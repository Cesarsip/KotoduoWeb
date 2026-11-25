#!/usr/bin/env bash
# Verificación pública: CP-DES-01, CP-DES-03 y las comprobaciones de la Tabla 9.
# Se ejecuta desde el equipo de desarrollo, contra la dirección pública
# (Informe 3, §8.3 y Tabla 11).
#
# Uso:
#   ./verificar.sh https://<ip-o-dominio> [usuario]
#
# La contraseña NUNCA va en el script: se lee de la variable KOTO_CLAVE o,
# en su defecto, de api/credenciales_semilla.txt (archivo fuera del repo).
# La salida queda en evidencias/despliegue/salida_verificacion_publica.txt.
set -uo pipefail

URL="${1:-}"
USUARIO="${2:-bjaque}"
[ -z "$URL" ] && { echo "uso: $0 https://<ip-o-dominio> [usuario]"; exit 2; }
URL="${URL%/}"

RAIZ="$(cd "$(dirname "$0")/../.." && pwd)"
SALIDA="$RAIZ/evidencias/despliegue/salida_verificacion_publica.txt"
mkdir -p "$(dirname "$SALIDA")"
FALLAS=0

if [ -z "${KOTO_CLAVE:-}" ] && [ -f "$RAIZ/api/credenciales_semilla.txt" ]; then
  KOTO_CLAVE="$(awk -v u="$USUARIO" '$1==u{print $3}' "$RAIZ/api/credenciales_semilla.txt" | head -1)"
fi
if [ -z "${KOTO_CLAVE:-}" ]; then
  echo "Define KOTO_CLAVE o deja api/credenciales_semilla.txt en su lugar."
  exit 2
fi

reg() {  # reg <PASS|FALLA|AVISO> <descripcion>
  printf '%s | %-6s | %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$1" "$2" | tee -a "$SALIDA"
  if [ "$1" = "FALLA" ]; then FALLAS=$((FALLAS + 1)); fi
}

http() { curl -sSL -o /dev/null -w '%{http_code}' --connect-timeout 10 --max-time 30 "$@"; }

{
  echo
  echo "==================================================================="
  echo "Verificación pública Kotoduo ($(date '+%d-%m-%Y %H:%M:%S'))"
  echo "URL: $URL"
  echo "==================================================================="
} | tee -a "$SALIDA"

# --- CP-DES-01: acceso público con la dirección elástica -------------------
CODIGO_LOGIN="$(http "$URL/")"
if [ "$CODIGO_LOGIN" = "200" ] && curl -sSL --max-time 30 "$URL/" | grep -qi "Iniciar sesión"; then
  reg PASS "CP-DES-01: la aplicación responde desde la dirección pública (se muestra el inicio de sesión)"
else
  reg FALLA "CP-DES-01: se esperaba 200 con la pantalla de inicio y llegó $CODIGO_LOGIN"
fi

# --- Tabla 9: inicio de sesión con una cuenta de prueba -------------------
TOKEN="$(printf '{"usuario":"%s","password":"%s"}' "$USUARIO" "$KOTO_CLAVE" \
         | curl -sSL -X POST "$URL/auth/login" -H 'Content-Type: application/json' \
           --data @- --max-time 30 | tr -d '\n' | sed -n 's/.*"token":"\([^"]*\)".*/\1/p')"
if [ -n "$TOKEN" ]; then
  reg PASS "Tabla 9: el inicio de sesión funciona con la cuenta $USUARIO (token emitido)"
else
  reg FALLA "Tabla 9: el inicio de sesión con $USUARIO no devolvió token"
fi

# --- Tabla 9: la interfaz habla con la API ---------------------------------
if [ -n "$TOKEN" ]; then
  COD="KTO-2026-$(printf '%03d' $((RANDOM % 900 + 100)))"
  ALTA="$(printf '{"codigo":"%s","tipo_trabajo":"uniforme","cliente_etiqueta":"Verificacion publica","unidades":5,"medidas":"20x30 cm","fecha_compromiso":"2026-12-24"}' "$COD" \
          | curl -sSL -o /dev/null -w '%{http_code}' -X POST "$URL/trabajos" \
            -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
            --data @- --max-time 30)"
  VISIBLE="$(curl -sSL -H "Authorization: Bearer $TOKEN" --max-time 30 "$URL/trabajos" | grep -c "$COD" || true)"
  if [ "$ALTA" = "201" ] && [ "$VISIBLE" -ge 1 ]; then
    reg PASS "Tabla 9: la interfaz habla con la API (alta $COD creada y visible en /trabajos)"
  else
    reg FALLA "Tabla 9: alta de trabajo devolvió $ALTA y aparece $VISIBLE veces en /trabajos"
  fi
fi

# --- CP-DES-03: rechazo de peticiones sin sesión desde internet ------------
CODIGO_TABLERO="$(http "$URL/tablero")"
if [ "$CODIGO_TABLERO" = "401" ]; then
  reg PASS "CP-DES-03: /tablero sin token responde 401 desde la dirección pública"
else
  reg FALLA "CP-DES-03: /tablero sin token devolvió $CODIGO_TABLERO (se esperaba 401)"
fi

CODIGO_USUARIOS="$(http "$URL/usuarios")"
if [ "$CODIGO_USUARIOS" = "401" ]; then
  reg PASS "Tabla 9: /usuarios sin token también responde 401"
else
  reg FALLA "Tabla 9: /usuarios sin token devolvió $CODIGO_USUARIOS (se esperaba 401)"
fi

# --- RNF-07: tránsito cifrado ----------------------------------------------
case "$URL" in
  https://*)
    ORIGEN="${URL#https://}"
    CODIGO_HTTP="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 15 "http://$ORIGEN/")"
    if [ "$CODIGO_HTTP" = "301" ] || [ "$CODIGO_HTTP" = "302" ]; then
      reg PASS "RNF-07: HTTP redirige a HTTPS ($CODIGO_HTTP)"
    else
      reg FALLA "RNF-07: http:// no redirige a HTTPS (devolvió $CODIGO_HTTP)"
    fi
    ;;
  *)
    reg AVISO "RNF-07: URL en HTTP; emitir el certificado con certbot (RUNBOOK §3)"
    ;;
esac

# --- CP-DES-02 y pruebas en el servidor: ver por separado ------------------
reg AVISO "CP-DES-02 (persistencia tras reinicio): ejecutar persistencia.sh"
reg AVISO "Pruebas en el servidor: mirar evidencias/despliegue/salida_pytest_servidor.txt"

{
  echo "-------------------------------------------------------------------"
  if [ "$FALLAS" -eq 0 ]; then
    echo "Resultado: TODAS LAS COMPROBACIONES PASARON"
  else
    echo "Resultado: $FALLAS COMPROBACION(ES) FALLIDA(S) - registrar en Tabla 8"
  fi
} | tee -a "$SALIDA"

exit "$FALLAS"
