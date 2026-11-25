# Runbook de despliegue — Kotoduo Producción

Guía operativa para publicar y mantener la aplicación en la nube.
Está escrita para que otra persona repita el proceso sin explicaciones
verbales, tal como exige el Informe 3, §8.2. Cada paso indica qué comando
corre, qué evidencia deja y en qué campo de la Tabla 8 se registra.

**Regla de oro:** ninguna contraseña, llave privada ni token aparece en este
repositorio, en la Tabla 8 ni en las evidencias. Las credenciales viven en
`api/credenciales_semilla.txt` (fuera del repo) o en variables de entorno.

---

## 1. Arquitectura publicada

```
Navegador (usuario)
   │  HTTPS 443
   ▼
Nginx  ── termina HTTPS y envía todo a Uvicorn
   │  HTTP 127.0.0.1:8000
   ▼
Uvicorn (systemd, 1 proceso, usuario ubuntu)
   │  sirve la API y los archivos de prototipo/
   ├── datos/kotoduo.db      SQLite      (estado operativo)
   └── datos/documentos.json TinyDB      (fichas de diseño)
```

- Proceso único con `workers=1`: las sesiones viven en memoria (§7.1).
- Uvicorn monta `prototipo/` como interfaz estática; `datos/` queda fuera del
  montaje, así que **las bases de datos no son servibles** aunque la
  aplicación falle.
- La comprobación de vida es `GET /`: responde 200 con la pantalla de
  inicio, sin sesión y sin exponer datos.

**Nota de la instancia publicada (25-11-2026).** El servicio corre como
`ubuntu`, con `WorkingDirectory=/home/ubuntu/KotoduoWeb/api` y el proyecto en
`/home/ubuntu/KotoduoWeb`; los respaldos van a `/home/ubuntu/backups`. Los
scripts de `despliegue/scripts/` conservan `/opt/kotoduo` y el usuario
`kotoduo` como valores por defecto para una instalación nueva; en esta
instancia se usaron las rutas reales que indica este runbook.

## 2. Requisitos

| Requisito | Detalle |
|-----------|---------|
| Instancia EC2 | Ubuntu Server 26.04.1 LTS, t3.micro o t3.small, par de llaves `.pem` |
| Grupo de seguridad | 22 solo desde la IP de desarrollo; 80 y 443 desde cualquier lugar |
| IP elástica | Asociada a la instancia (dirección fija registrada en Tabla 8) |
| Dominio | Un registro apuntando a la IP (DuckDNS sirve); para HTTPS con Let's Encrypt |
| Equipo de desarrollo | Python 3.11+, `rsync`, `ssh`, `curl` |

## 3. Aprovisionamiento (una sola vez, §8.2 B.1 a B.3)

```bash
# desde el equipo de desarrollo
scp -i clave_kotoduo.pem despliegue/scripts/preparar_servidor.sh ubuntu@<IP>:
ssh -i clave_kotoduo.pem ubuntu@<IP> 'bash preparar_servidor.sh <IP-DE-DESARROLLO>'
```

El script instala paquetes, crea el usuario `kotoduo`, configura UFW (22
restringido a la IP de desarrollo), activa fail2ban y deja sudo sin contraseña
solo para los cinco comandos de despliegue. Luego se asocia la IP elástica en
la consola de AWS. En la instancia publicada se trabajó con el usuario
`ubuntu` y la ruta `/home/ubuntu/KotoduoWeb`; el script queda como plantilla
para una instalación nueva con usuario y ruta dedicados.

**Tabla 8:** *Sistema operativo* (`lsb_release -ds`), *Llave de acceso* (solo
el nombre del archivo `.pem`), *Comandos principales ejecutados*.

## 4. Despliegue (§8.2 B.4 a B.7)

```bash
./despliegue/scripts/desplegar.sh ubuntu@<IP> clave_kotoduo.pem
```

Qué hace, en orden:

1. Sube `api/`, `prototipo/`, `datos/`, `evidencias/`, `despliegue/` y el
   `requirements.txt`. **Excluye** `kotoduo.db`, `documentos.json`,
   `credenciales_semilla.txt` y llaves: nunca sobreescribe datos del servidor.
2. Crea/actualiza el entorno virtual con las versiones exactas de la Tabla 7.
3. Reconstruye la base **solo si no existe**.
4. Corre `pytest` contra copias en `/tmp` (`KOTODUO_DB` y
   `KOTODUO_DOC_DB`): si algo falla, el despliegue se aborta antes de
   reiniciar. Evidencia: `evidencias/despliegue/salida_pytest_servidor.txt`.
   **Nunca** ejecutar `pytest` sin esas variables en la instancia publicada:
   `conftest.py` reconstruye la base y borraría los datos de producción.
5. Reinicia el servicio systemd y recarga Nginx.
6. Comprueba que `GET /` responde 200 (pantalla de inicio).

**Tabla 8:** *Salida de las pruebas en el servidor* (Anexo J),
*Comandos principales ejecutados*.

## 5. Certificado HTTPS (§8.2 B.10, RNF-07)

```bash
ssh -i clave_kotoduo.pem ubuntu@<IP>
# editar server_name en /etc/nginx/sites-available/kotoduo.conf
sudo nano /etc/nginx/sites-available/kotoduo.conf
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d <dominio> --redirect --hsts --uir
```

Certbot reescribe el bloque `server` y agrega la redirección. Verificar luego
con `verificar.sh https://<dominio>` (incluye la comprobación de redirección).

**Tabla 8:** *Interfaz publicada en* (URL completa con https).

## 6. Verificación pública (§8.3)

```bash
# CP-DES-01, CP-DES-03 y Tabla 9 desde la dirección pública
./despliegue/scripts/verificar.sh https://<dominio>

# CP-DES-02 (persistencia tras reinicio), en dos fases
./despliegue/scripts/persistencia.sh https://<dominio>        # antes
#   -> reiniciar la instancia desde la consola AWS
./despliegue/scripts/persistencia.sh https://<dominio> --despues
```

Salidas: `evidencias/despliegue/verificacion_despliegue_2026-11-25.txt` y
`evidencias/despliegue/verificacion_persistencia_2026-11-25.txt`.

| Caso | Qué comprueba | Estado |
|------|---------------|--------|
| CP-DES-01 | URL pública muestra el inicio de sesión y el login emite token | Aprobado 25-11-2026 |
| CP-DES-02 | `KTO-2026-014` sigue presente tras reiniciar la instancia | Aprobado 25-11-2026 (reinicio real) |
| CP-DES-03 | `/tablero` y `/usuarios` sin token responden 401 desde internet | Aprobado 25-11-2026 |

Si algo falla, se registra como incidencia en la Tabla 8 **sin borrar el
primer intento** (§9.3).

### Capturas desde la dirección pública

```bash
# reconstruir semilla local primero
python datos/ejecutar_datos.py && python datos/crear_documentos.py
KOTODUO_URL=https://<dominio>/ python evidencias/capturas/capturar.py
```

`capturar.py` usa `KOTODUO_URL`, así que las nueve capturas se regeneran
idénticas pero tomadas desde la URL pública (§5.3).

## 7. Respaldos (Tabla 8)

```bash
# instalar el cron de respaldo diario a las 03:00 UTC (retención 14 días)
(crontab -l 2>/dev/null | grep -v 'despliegue/scripts/respaldo.sh'; \
 echo '0 3 * * * /home/ubuntu/KotoduoWeb/despliegue/scripts/respaldo.sh >> /home/ubuntu/backups/respaldo.log 2>&1') | crontab -
```

- Destino: `/home/ubuntu/backups/` (`kotoduo-AAAA-MM-DD_HHMM.db` + `documentos-*.json`).
- Copia con la API de copia segura de SQLite (`.backup`), sin detener el servicio.
- Verificación de integridad (`PRAGMA integrity_check`) en cada ejecución.
- Primera ejecución registrada: `respaldo ok`, integridad `ok`, 25-11-2026.

**Restauración:**

```bash
sudo systemctl stop kotoduo
sudo cp /home/ubuntu/backups/kotoduo-<fecha>.db /home/ubuntu/KotoduoWeb/datos/kotoduo.db
sudo chown ubuntu:ubuntu /home/ubuntu/KotoduoWeb/datos/kotoduo.db
sudo systemctl start kotoduo
```

**Tabla 8:** *Ubicación de kotoduo.db y documentos.json, y frecuencia de
respaldo* → `/home/ubuntu/KotoduoWeb/datos/`, respaldo diario 03:00 UTC en
`/home/ubuntu/backups/`, retención 14 días.

## 8. Monitoreo y operación diaria

```bash
# estado y errores del servicio
systemctl status kotoduo
journalctl -u kotoduo -f              # errores en vivo
journalctl -u kotoduo --since today

# accesos y errores de Nginx
tail -f /var/log/nginx/kotoduo.access.log
grep -E ' (5[0-9]{2}|429) ' /var/log/nginx/kotoduo.access.log | tail -50

# comprobación de vida: la pantalla de inicio debe responder 200
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8000/
```

Alertas a atender: `GET /` sin 200, ráfagas de 429 en `/auth/login`
(intento de fuerza bruta), errores 5xx, y respaldos con `RESPALDO CORRUPTO`.

## 9. Rollback

El código en el servidor es un espejo del repositorio: para volver a una
versión anterior, en el equipo de desarrollo:

```bash
git checkout <commit-anterior>
./despliegue/scripts/desplegar.sh ubuntu@<IP> clave_kotoduo.pem
git checkout main
```

El despliegue nunca toca `datos/` del servidor, así que los datos sobreviven
al rollback. Si el rollback no resuelve: `sudo systemctl stop kotoduo` y
registrar la incidencia en la Tabla 8.

## 10. Mapeo Tabla 8 ← fuente de cada valor

| Campo de la Tabla 8 | Fuente |
|---------------------|--------|
| Fecha del despliegue | `date` en el servidor / primera línea de `salida_verificacion_publica.txt` |
| Sistema operativo | `lsb_release -ds` |
| Versiones (Python, Uvicorn, Nginx) | `python3 -V`, `.venv/bin/uvicorn --version`, `nginx -v` |
| Dirección IP elástica | Consola AWS → Elastic IPs |
| Llave de acceso (solo nombre) | Nombre del `.pem`, nunca el contenido |
| Comandos principales | §4 y §5 de este runbook |
| Salida de pruebas en el servidor | `evidencias/despliegue/salida_pytest_servidor.txt` |
| Interfaz publicada en | URL HTTPS usada en `verificar.sh` |
| Ubicación de las bases y respaldo | §7 de este runbook |
| Incidencias | Todo lo marcado `FALLA` en `salida_verificacion_publica.txt` |

## 11. Checklist de entrega

- [x] IP elástica asociada y registrada en Tabla 8 (184.193.153.190)
- [x] HTTPS activo con redirección (RNF-07; Let's Encrypt hasta 22-02-2027)
- [x] CP-DES-01 aprobado (25-11-2026)
- [x] CP-DES-02 aprobado (reinicio real, 25-11-2026)
- [x] CP-DES-03 aprobado (401 desde internet, 25-11-2026)
- [x] `salida_pytest_servidor.txt` con 17 pruebas aprobadas
- [x] Cron de respaldo instalado y primera ejecución con `respaldo ok` (25-11-2026)
- [x] Capturas públicas de login y vendedor agregadas al Anexo J
- [x] Tabla 8 completa, sin secretos
