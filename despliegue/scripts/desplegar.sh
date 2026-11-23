#!/usr/bin/env bash
# Despliegue repetible al servidor (Informe 3, §8.2 B.4 a B.7).
# Se ejecuta desde el equipo de desarrollo.
#
# Uso:
#   ./desplegar.sh <usuario@host> [clave.pem]
#   ./desplegar.sh ubuntu@203.0.113.10 clave_kotoduo.pem
#
# Garantías:
#   · Nunca sube la base de datos del servidor ni credenciales
#     (datos/kotoduo.db, datos/documentos.json y credenciales_semilla.txt
#     quedan fuera de la transferencia).
#   · Las pruebas corren contra una copia en /tmp: no tocan la base real.
#   · Si una prueba falla, el despliegue se aborta antes de reiniciar.
set -euo pipefail

DESTINO="${1:-}"
LLAVE="${2:-}"
[ -z "$DESTINO" ] && { echo "uso: $0 <usuario@host> [clave.pem]"; exit 2; }

RAIZ="$(cd "$(dirname "$0")/../.." && pwd)"
SSH_OPTS=(-o StrictHostKeyChecking=accept-new -o ConnectTimeout=10)
[ -n "$LLAVE" ] && SSH_OPTS+=(-i "$LLAVE")
RSYNC_RSH="ssh ${SSH_OPTS[*]}"

paso() { printf '\n==> %s\n' "$1"; }
remoto() { ssh "${SSH_OPTS[@]}" "$DESTINO" 'bash -s'; }

paso "1/6 Subiendo el proyecto a $DESTINO:/opt/kotoduo"
rsync -az -e "$RSYNC_RSH" --delete \
      --exclude '__pycache__' --exclude '.pytest_cache' --exclude '*.pyc' \
      --exclude 'credenciales_semilla.txt' --exclude '*.pem' --exclude '*.key' \
      "$RAIZ/api/" "$DESTINO:/opt/kotoduo/api/"
rsync -az -e "$RSYNC_RSH" --delete \
      --exclude '__pycache__' \
      "$RAIZ/prototipo/" "$DESTINO:/opt/kotoduo/prototipo/"
rsync -az -e "$RSYNC_RSH" \
      --exclude 'kotoduo.db' --exclude 'documentos.json' \
      "$RAIZ/datos/" "$DESTINO:/opt/kotoduo/datos/"
rsync -az -e "$RSYNC_RSH" \
      --exclude 'despliegue/*.txt' --exclude 'despliegue/.*' \
      "$RAIZ/evidencias/" "$DESTINO:/opt/kotoduo/evidencias/"
rsync -az -e "$RSYNC_RSH" "$RAIZ/despliegue/" "$DESTINO:/opt/kotoduo/despliegue/"
rsync -az -e "$RSYNC_RSH" "$RAIZ/requirements.txt" "$RAIZ/README.md" "$DESTINO:/opt/kotoduo/"
echo "    archivos subidos"

paso "2/6 Entorno virtual y dependencias (versiones exactas de la Tabla 7)"
remoto <<'REMOTO'
set -euo pipefail
cd /opt/kotoduo
[ -d .venv ] || python3 -m venv .venv
.venv/bin/pip install --disable-pip-version-check -q -r requirements.txt
.venv/bin/python -c "import fastapi, uvicorn, tinydb, argon2, pytest; print('    dependencias OK')"
chgrp -R kotoduo .venv 2>/dev/null || true
REMOTO

paso "3/6 Base de datos: solo se reconstruye si no existe"
remoto <<'REMOTO'
set -euo pipefail
cd /opt/kotoduo
if [ -f datos/kotoduo.db ]; then
  echo "    base existente conservada (nunca se sobreescribe en el despliegue)"
else
  .venv/bin/python datos/ejecutar_datos.py >/dev/null
  .venv/bin/python datos/crear_documentos.py >/dev/null
  echo "    base reconstruida desde el esquema y la semilla"
fi
REMOTO

paso "4/6 Pruebas en el servidor (sobre una copia en /tmp, no sobre producción)"
remoto <<'REMOTO'
set -euo pipefail
cd /opt/kotoduo
mkdir -p evidencias/despliegue
KOTODUO_DB=/tmp/kotoduo_test.db KOTODUO_DOC_DB=/tmp/kotoduo_test.json \
  .venv/bin/python -m pytest api/ -q 2>&1 | tee evidencias/despliegue/salida_pytest_servidor.txt
rm -f /tmp/kotoduo_test.db /tmp/kotoduo_test.json
REMOTO

paso "5/6 Servicio systemd y Nginx"
remoto <<'REMOTO'
set -euo pipefail
sudo -n nginx -t
sudo -n systemctl daemon-reload
sudo -n systemctl restart kotoduo
sudo -n systemctl reload nginx
sleep 1
echo "    servicio: $(systemctl is-active kotoduo) / habilitado: $(systemctl is-enabled kotoduo)"
REMOTO

paso "6/6 Sonda de salud local"
SALUD="$(ssh "${SSH_OPTS[@]}" "$DESTINO" 'curl -fsS http://127.0.0.1:8000/health')"
echo "    $SALUD"

echo
echo "Despliegue terminado."
echo "Siguiente: emitir el certificado (RUNBOOK §3) y correr verificacion con verificar.sh"
