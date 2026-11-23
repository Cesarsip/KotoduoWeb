#!/usr/bin/env bash
# Aprovisionamiento de la instancia EC2 (Informe 3, §8.2 B.1 y B.2).
# Se ejecuta una sola vez, como usuario de la consola (ubuntu), con sudo.
#
# Uso:
#   ./preparar_servidor.sh <ip-equipo-desarrollo> [usuario-despliegue] [zona-horaria]
#   ./preparar_servidor.sh 190.45.10.22 ubuntu America/Santiago
#
# El puerto 22 queda abierto SOLO desde la IP del equipo de desarrollo y
# 80/443 desde cualquier lugar, tal como pide el paso 2 del protocolo.
set -euo pipefail

IP_DEV="${1:-}"
USUARIO_DESPLIEGUE="${2:-ubuntu}"
ZONA="${3:-America/Santiago}"
[ -z "$IP_DEV" ] && { echo "uso: $0 <ip-equipo-desarrollo> [usuario-despliegue] [zona-horaria]"; exit 2; }

paso() { printf '\n==> %s\n' "$1"; }

paso "1/7 Paquetes del sistema (Python, Nginx, certbot, sqlite3, UFW, fail2ban)"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq --no-install-recommends \
    python3 python3-venv python3-pip sqlite3 curl \
    nginx certbot python3-certbot-nginx ufw fail2ban

paso "2/7 Hora del sistema"
timedatectl set-timezone "$ZONA"
date

paso "3/7 Usuario de servicio y directorios"
id -u kotoduo >/dev/null 2>&1 || useradd --system --home-dir /opt/kotoduo \
    --shell /usr/sbin/nologin --comment "Kotoduo Produccion" kotoduo
mkdir -p /opt/kotoduo /var/backups/kotoduo
# El usuario de despliegue escribe en el mismo grupo (setgid hereda el grupo
# en los archivos nuevos, para que el servicio siempre pueda leerlos).
usermod -aG kotoduo "$USUARIO_DESPLIEGUE"

paso "4/7 Grupo de seguridad: 22 solo desde la IP de desarrollo, 80/443 abiertos"
ufw default deny incoming
ufw default allow outgoing
ufw allow from "$IP_DEV" to any port 22 proto tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable
ufw status verbose

paso "5/7 Protección SSH con fail2ban"
systemctl enable --now fail2ban
systemctl is-active fail2ban

paso "6/7 Permisos de despliegue sin contraseña (solo comandos puntuales)"
cat > /etc/sudoers.d/kotoduo-despliegue <<EOF
# Despliegue automatizado: solo estos comandos, sin contraseña.
$USUARIO_DESPLIEGUE ALL=(root) NOPASSWD: /usr/bin/systemctl restart kotoduo, /usr/bin/systemctl reload nginx, /usr/bin/systemctl is-active kotoduo, /usr/bin/systemctl daemon-reload, /usr/bin/nginx -t
EOF
chmod 0440 /etc/sudoers.d/kotoduo-despliegue
visudo -cf /etc/sudoers.d/kotoduo-despliegue

paso "7/7 Permisos de escritura en /opt/kotoduo"
chown -R "$USUARIO_DESPLIEGUE":kotoduo /opt/kotoduo
chmod -R g+rwX /opt/kotoduo
find /opt/kotoduo -type d -exec chmod g+s {} +

echo
echo "Servidor preparado."
echo "Siguiente paso: subir el proyecto con desplegar.sh y emitir el certificado (RUNBOOK §3)."
