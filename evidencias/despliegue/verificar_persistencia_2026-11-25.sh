#!/usr/bin/env bash
# ============================================================
# Kotoduo Produccion - Persistencia tras reiniciar la instancia
# Fecha: 25-11-2026
# Uso (en el servidor): bash evidencias/despliegue/verificar_persistencia_2026-11-25.sh
# ============================================================
set -u

RAIZ="/home/ubuntu/KotoduoWeb"
DB="$RAIZ/datos/kotoduo.db"
PY="$RAIZ/.venv/bin/python"
cd "$RAIZ" || exit 1

sep() { printf '%s\n' "------------------------------------------------------------"; }

sep
echo "CP-DES-02. Estado de la base DESPUES del reinicio"
sep
echo "Fecha (UTC) ......... $(date -u '+%Y-%m-%d %H:%M:%S')"
echo "Encendido desde ..... $(uptime -s) UTC"
echo "Tiempo encendido .... $(uptime -p)"
echo "Servicio kotoduo .... $(systemctl is-active kotoduo) ($(systemctl is-enabled kotoduo 2>/dev/null))"
echo

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
echo "ACCESO PUBLICO DESPUES DEL REINICIO"
sep
URL="${KOTODUO_URL:-https://kotoduo.duckdns.org}"
curl -s -o /dev/null -w "  GET / ...................... %{http_code}\n" "$URL/"
curl -s -o /dev/null -w "  GET /tablero sin token ..... %{http_code}\n" "$URL/tablero"
echo

sep
echo "FIN DE LA VERIFICACION DE PERSISTENCIA"
sep
