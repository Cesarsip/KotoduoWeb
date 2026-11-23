#!/usr/bin/env bash
# CP-DES-02: los datos persisten tras reiniciar la instancia (Tabla 9 y
# Tabla 11). Dos fases, para que el reinicio sea real y no simulado:
#
#   Fase 1 (antes de reiniciar):   ./persistencia.sh https://<ip>
#   -> en la consola de AWS: Stop instance -> Start instance
#      (o: ssh usuario@host 'sudo reboot')
#   Fase 2 (después de reiniciar): ./persistencia.sh https://<ip> --despues
#
# Compara el registro KTO-2026-014 antes y después del reinicio.
# La salida queda en evidencias/despliegue/salida_persistencia.txt.
set -uo pipefail

URL="${1:-}"
MODO="${2:-antes}"
[ -z "$URL" ] && { echo "uso: $0 https://<ip-o-dominio> [--despues]"; exit 2; }
URL="${URL%/}"

RAIZ="$(cd "$(dirname "$0")/../.." && pwd)"
SALIDA="$RAIZ/evidencias/despliegue/salida_persistencia.txt"
MARCADOR="$RAIZ/evidencias/despliegue/.persistencia_antes.json"
CODIGO="KTO-2026-014"
USUARIO="jrojas"
mkdir -p "$(dirname "$SALIDA")"

KOTO_CLAVE="${KOTO_CLAVE:-}"
if [ -z "$KOTO_CLAVE" ] && [ -f "$RAIZ/api/credenciales_semilla.txt" ]; then
  KOTO_CLAVE="$(awk -v u="$USUARIO" '$1==u{print $3}' "$RAIZ/api/credenciales_semilla.txt" | head -1)"
fi
if [ -z "$KOTO_CLAVE" ]; then
  echo "Define KOTO_CLAVE o deja api/credenciales_semilla.txt en su lugar."
  exit 2
fi

reg() {
  printf '%s | %-6s | %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$1" "$2" | tee -a "$SALIDA"
}

TOKEN="$(printf '{"usuario":"%s","password":"%s"}' "$USUARIO" "$KOTO_CLAVE" \
         | curl -sSL -X POST "$URL/auth/login" -H 'Content-Type: application/json' \
           --data @- --max-time 30 | tr -d '\n' | sed -n 's/.*"token":"\([^"]*\)".*/\1/p')"
if [ -z "$TOKEN" ]; then
  reg FALLA "CP-DES-02: no se pudo iniciar sesión como $USUARIO en $URL"
  exit 1
fi

FICHA="$(curl -sSL -H "Authorization: Bearer $TOKEN" --max-time 30 "$URL/trabajos/$CODIGO/estado")"

if [ "$MODO" = "antes" ]; then
  if echo "$FICHA" | grep -q "\"codigo\":\"$CODIGO\""; then
    printf '%s' "$FICHA" > "$MARCADOR"
    reg PASS "CP-DES-02 fase 1: $CODIGO registrado antes del reinicio -> $MARCADOR"
    echo
    echo "Ahora reinicia la instancia (consola AWS o 'sudo reboot' por ssh) y"
    echo "vuelve a ejecutar:  $0 $URL --despues"
  else
    reg FALLA "CP-DES-02 fase 1: $CODIGO no responde antes del reinicio"
    exit 1
  fi
  exit 0
fi

if [ ! -f "$MARCADOR" ]; then
  echo "Falta la fase 1: ejecuta antes $0 $URL"
  exit 2
fi
ANTES="$(cat "$MARCADOR")"
ESTADO_ANTES="$(echo "$ANTES" | sed -n 's/.*"estado_general":"\([^"]*\)".*/\1/p')"
ESTADO_DESPUES="$(echo "$FICHA" | sed -n 's/.*"estado_general":"\([^"]*\)".*/\1/p')"

if echo "$FICHA" | grep -q "\"codigo\":\"$CODIGO\"" && \
   [ -n "$ESTADO_DESPUES" ] && [ "$ESTADO_DESPUES" = "$ESTADO_ANTES" ]; then
  reg PASS "CP-DES-02: $CODIGO sigue presente tras el reinicio (estado $ESTADO_DESPUES, igual que antes)"
else
  reg FALLA "CP-DES-02: después del reinicio $CODIGO devolvió '$ESTADO_DESPUES' y antes '$ESTADO_ANTES'"
  exit 1
fi

reg PASS "CP-DES-02 completado"
exit 0
