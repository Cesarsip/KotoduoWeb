#!/usr/bin/env bash
# ============================================================
# Kotoduo Produccion - Verificacion del despliegue en EC2
# Fecha: 25-11-2026
# Uso (en el servidor): bash evidencias/despliegue/verificar_despliegue_2026-11-25.sh
# No imprime contrasenas ni tokens: solo codigos HTTP y datos de la base.
# ============================================================
set -u

URL="${KOTODUO_URL:-https://kotoduo.duckdns.org}"
RAIZ="/home/ubuntu/KotoduoWeb"
DB="$RAIZ/datos/kotoduo.db"
PY="$RAIZ/.venv/bin/python"
cd "$RAIZ" || exit 1

sep() { printf '%s\n' "------------------------------------------------------------"; }
token_imds() {
  curl -s --max-time 4 -X PUT http://169.254.169.254/latest/api/token \
    -H 'X-aws-ec2-metadata-token-ttl-seconds: 60'
}

sep
echo "VERIFICACION DEL DESPLIEGUE - KOTODUO PRODUCCION"
sep
echo "Fecha (UTC) ......... $(date -u '+%Y-%m-%d %H:%M:%S')"
echo "Instancia EC2 ....... $(curl -s --max-time 4 -H "X-aws-ec2-metadata-token: $(token_imds)" http://169.254.169.254/latest/meta-data/instance-id)"
echo "Region .............. $(curl -s --max-time 4 -H "X-aws-ec2-metadata-token: $(token_imds)" http://169.254.169.254/latest/meta-data/placement/region)"
echo "Sistema operativo ... $(lsb_release -ds)"
echo "Python (venv) ....... $($PY --version 2>&1)"
echo "Uvicorn ............. $($PY -m uvicorn --version 2>&1)"
echo "Nginx ............... $(nginx -v 2>&1)"
echo "Servicio kotoduo .... $(systemctl is-active kotoduo) ($(systemctl is-enabled kotoduo 2>/dev/null))"
echo "URL publica ......... $URL"
echo

sep
echo "CP-DES-01. Acceso publico a la interfaz y a la API"
sep
curl -s -o /dev/null -w "  GET / ...................... %{http_code}\n" "$URL/"
curl -s -o /dev/null -w "  GET /styles.css ............ %{http_code}\n" "$URL/styles.css"
curl -s -o /dev/null -w "  GET /app.js ................ %{http_code}\n" "$URL/app.js"
curl -s -o /dev/null -w "  GET /openapi.json .......... %{http_code}\n" "$URL/openapi.json"

CLAVE=$(awk '$1=="aeo" {print $3}' api/credenciales_semilla.txt)
RESPUESTA=$(curl -s -X POST "$URL/auth/login" -H 'Content-Type: application/json' \
  -d "{\"usuario\":\"aeo\",\"password\":\"$CLAVE\"}")
ROL=$(printf '%s' "$RESPUESTA" | $PY -c "import json,sys; print(json.load(sys.stdin).get('rol',''))" 2>/dev/null)
TOKEN=$(printf '%s' "$RESPUESTA" | $PY -c "import json,sys; print(json.load(sys.stdin).get('token',''))" 2>/dev/null)
echo "  POST /auth/login ........... rol=$ROL, token=$([ -n "$TOKEN" ] && echo entregado || echo ausente)"
if [ -n "$TOKEN" ]; then
  curl -s -o /dev/null -w "  GET /tablero con sesion .... %{http_code}\n" -H "Authorization: Bearer $TOKEN" "$URL/tablero"
  curl -s -o /dev/null -w "  GET /trabajos con sesion ... %{http_code}\n" -H "Authorization: Bearer $TOKEN" "$URL/trabajos"
  curl -s -o /dev/null -w "  GET /insumos/alertas ....... %{http_code}\n" -H "Authorization: Bearer $TOKEN" "$URL/insumos/alertas"
fi
echo

sep
echo "CP-DES-03. Rechazo de peticiones sin sesion desde internet"
sep
curl -s -o /dev/null -w "  GET /tablero sin token ..... %{http_code}\n" "$URL/tablero"
curl -s -o /dev/null -w "  GET /tablero token falso ... %{http_code}\n" -H "Authorization: Bearer token.invalido.2026" "$URL/tablero"
curl -s -o /dev/null -w "  GET /bitacora sin token .... %{http_code}\n" "$URL/bitacora"
curl -s -o /dev/null -w "  GET /admin ................. %{http_code}\n" "$URL/admin"
echo

sep
echo "CP-DES-02. Estado de la base ANTES del reinicio"
sep
$PY - "$DB" <<'PY'
import sqlite3
import sys

con = sqlite3.connect(sys.argv[1])
con.row_factory = sqlite3.Row
q = lambda s: con.execute(s).fetchone()[0]

print(f"  Trabajos ................... {q('select count(*) from trabajos')}")
print(f"  Etapas ..................... {q('select count(*) from etapas_trabajo')}")
print(f"  Usuarios ................... {q('select count(*) from usuarios')}")
print(f"  Registros de bitacora ...... {q('select count(*) from bitacora')}")
print(f"  Insumos .................... {q('select count(*) from insumos')}")
fila = con.execute(
    "select codigo, estado_general, unidades from trabajos where codigo='KTO-2026-014'"
).fetchone()
print(f"  KTO-2026-014 ............... {dict(fila) if fila else 'NO ENCONTRADO'}")
print("  Sanidad de la base:")
print(f"    trabajos con unidades <= 0 ......... {q('select count(*) from trabajos where unidades <= 0')}")
print(f"    etapas sin trabajo valido .......... {q('select count(*) from etapas_trabajo e left join trabajos t on t.id=e.trabajo_id where t.id is null')}")
ROLES = "select count(*) from usuarios where rol not in ('operario','encargado','vendedor','administrador')"
print(f"    roles fuera del catalogo ........... {q(ROLES)}")
PY
echo

sep
echo "PRUEBAS AUTOMATIZADAS EN EL SERVIDOR"
sep
echo "  (sobre copias en /tmp: la base de produccion no se toca)"
KOTODUO_DB=/tmp/kotoduo_pruebas.db KOTODUO_DOC_DB=/tmp/documentos_pruebas.json \
  $PY -m pytest api/ -q > evidencias/despliegue/salida_pytest_servidor.txt 2>&1
CODIGO=$?
tail -3 evidencias/despliegue/salida_pytest_servidor.txt
echo "  Codigo de salida de pytest ... $CODIGO"
echo

sep
echo "FIN DE LA VERIFICACION PREVIA AL REINICIO"
echo "Siguiente paso: sudo reboot y, cuando la instancia vuelva,"
echo "bash evidencias/despliegue/verificar_persistencia_2026-11-25.sh"
sep
