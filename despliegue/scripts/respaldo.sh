#!/usr/bin/env bash
# Respaldo diario de las dos bases (Informe 3, Tabla 8: ubicacion y frecuencia).
# Se ejecuta por cron en la instancia, sin detener el servicio:
#
#   crontab -e
#   0 3 * * * /home/ubuntu/KotoduoWeb/despliegue/scripts/respaldo.sh >> /home/ubuntu/backups/respaldo.log 2>&1
#
# Retencion: 14 dias. Los respaldos quedan en /home/ubuntu/backups/.
set -euo pipefail

RAIZ="${KOTODUO_RAIZ:-/home/ubuntu/KotoduoWeb}"
DESTINO="${KOTODUO_RESPALDOS:-/home/ubuntu/backups}"
RETENCION_DIAS=14
FECHA="$(date -u +%Y-%m-%d_%H%M)"
ORIGEN_DB="$RAIZ/datos/kotoduo.db"
ORIGEN_JSON="$RAIZ/datos/documentos.json"
PY="$RAIZ/.venv/bin/python"

mkdir -p "$DESTINO"
[ -f "$ORIGEN_DB" ] || { echo "$(date -u) no existe $ORIGEN_DB"; exit 1; }

# sqlite3.Connection.backup usa la API de copia en linea: no interfiere con
# las escrituras del servicio y deja un archivo consistente.
"$PY" - "$ORIGEN_DB" "$DESTINO/kotoduo-$FECHA.db" <<'PY'
import sqlite3
import sys

origen, destino = sys.argv[1], sys.argv[2]
con = sqlite3.connect(origen)
respaldo = sqlite3.connect(destino)
with respaldo:
    con.backup(respaldo)
respaldo.close()
con.close()
PY

cp -f "$ORIGEN_JSON" "$DESTINO/documentos-$FECHA.json" 2>/dev/null || true

INTEGRIDAD="$("$PY" - "$DESTINO/kotoduo-$FECHA.db" <<'PY'
import sqlite3
import sys

print(sqlite3.connect(sys.argv[1]).execute("PRAGMA integrity_check;").fetchone()[0])
PY
)"
if [ "$INTEGRIDAD" != "ok" ]; then
  echo "$(date -u) RESPALDO CORRUPTO: $DESTINO/kotoduo-$FECHA.db ($INTEGRIDAD)"
  exit 1
fi

find "$DESTINO" -maxdepth 1 -name 'kotoduo-*.db' -mtime "+$RETENCION_DIAS" -delete
find "$DESTINO" -maxdepth 1 -name 'documentos-*.json' -mtime "+$RETENCION_DIAS" -delete

echo "$(date -u) respaldo ok: kotoduo-$FECHA.db (integridad $INTEGRIDAD), retencion ${RETENCION_DIAS}d"
