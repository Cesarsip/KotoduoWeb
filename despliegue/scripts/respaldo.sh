#!/usr/bin/env bash
# Respaldo diario de las dos bases (Informe 3, Tabla 8: ubicación y frecuencia).
# Se instala en el servidor y se ejecuta por cron, como root:
#
#   sudo cp respaldo.sh /opt/kotoduo/despliegue/scripts/respaldo.sh
#   echo '0 3 * * * root /opt/kotoduo/despliegue/scripts/respaldo.sh >> /var/log/kotoduo-respaldo.log 2>&1' \
#     | sudo tee /etc/cron.d/kotoduo-respaldo
#
# Retención: 14 días. Los respaldos quedan en /var/backups/kotoduo/.
set -euo pipefail

ORIGEN_DB="/opt/kotoduo/datos/kotoduo.db"
ORIGEN_JSON="/opt/kotoduo/datos/documentos.json"
DESTINO="/var/backups/kotoduo"
RETENCION_DIAS=14
FECHA="$(date +%F_%H%M)"

mkdir -p "$DESTINO"
[ -f "$ORIGEN_DB" ] || { echo "$(date) no existe $ORIGEN_DB"; exit 1; }

# .backup usa la API de copia segura de SQLite: no interfiere con el servicio.
sqlite3 "$ORIGEN_DB" ".backup '$DESTINO/kotoduo-$FECHA.db'"
cp -f "$ORIGEN_JSON" "$DESTINO/documentos-$FECHA.json" 2>/dev/null || true

INTEGRIDAD="$(sqlite3 "$DESTINO/kotoduo-$FECHA.db" 'PRAGMA integrity_check;')"
if [ "$INTEGRIDAD" != "ok" ]; then
  echo "$(date) RESPALDO CORRUPTO: $DESTINO/kotoduo-$FECHA.db ($INTEGRIDAD)"
  exit 1
fi

find "$DESTINO" -name 'kotoduo-*.db'     -mtime "+$RETENCION_DIAS" -delete
find "$DESTINO" -name 'documentos-*.json' -mtime "+$RETENCION_DIAS" -delete

echo "$(date) respaldo ok: kotoduo-$FECHA.db (integridad $INTEGRIDAD), retención ${RETENCION_DIAS}d"
