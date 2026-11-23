# Kotoduo Producción

Sistema de gestión de producción del taller textil y de rótulos **Kotoduo**:
trabajos, etapas, aprobación de diseños, alertas de insumos, usuarios y bitácora.

Proyecto Integrado ES3 — Unidad 3 (implementación y validación).
Autores: César Aedo y Benjamín Jaque.

## Qué incluye

| Ruta | Contenido |
|------|-----------|
| `api/app.py` | API REST en FastAPI y servidor de la interfaz (un solo proceso Uvicorn) |
| `api/test_app.py` | Plan de pruebas automatizadas: UT-01..04, IN-01..06, SEG-01..06, RND-01 |
| `datos/kotoduo_schema.sql` | Esquema relacional (SQLite / DDL de producción para PostgreSQL) |
| `datos/kotoduo_datos.sql` | Datos de ejemplo coherentes con el caso (sin montos ni contactos) |
| `datos/ejecutar_datos.py` | Reconstruye la base, ejecuta el DDL y captura `salida_ddl.txt` |
| `datos/crear_documentos.py` | Base documental TinyDB (`documentos.json`) y `salida_documentos.txt` |
| `prototipo/` | Interfaz web (HTML/CSS/JS) servida por la misma API |
| `evidencias/` | Capturas, diagramas y salidas de ejecución |

## Puesta en marcha (protocolo §8.2 A)

Requiere Python 3.11 o superior.

```bash
pip install -r requirements.txt

# 1) reconstruir la base y las evidencias de datos
python datos/ejecutar_datos.py
python datos/crear_documentos.py

# 2) ejecutar las pruebas
pytest api/ -q
bandit -r api/app.py

# 3) arrancar API e interfaz en un solo proceso
cd api
uvicorn app:app --host 127.0.0.1 --port 8000
```

La interfaz queda en `http://127.0.0.1:8000/` y la documentación interactiva
de la API en `http://127.0.0.1:8000/docs`.

## Perfiles de prueba

Cuatro roles con permisos distintos, verificados en el servidor (401 sin sesión,
403 sin permiso). Las credenciales de la semilla se generan con argon2id en
`datos/ejecutar_datos.py`; **no se publican contraseñas ni llaves en este
repositorio** (Informe 3, §8.2).

| Rol | Perfil | Pantalla de inicio |
|-----|--------|--------------------|
| Operario | `msanchez` | Mis tareas de hoy |
| Encargado de producción | `bjaque` | Tablero de producción |
| Vendedor | `jrojas` | Estado de un pedido |
| Administrador | `aeo` | Usuarios y bitácora |

## Alcance declarado

- Cero dinero: la API solo guarda `pedido_ref`; no hay montos, precios ni
  contactos de clientes.
- Bitácora inmutable: cada acción queda registrada con usuario, fecha y valores.
- Dos bases de datos: SQLite para el estado operativo y TinyDB para las fichas
  de diseño (HU-06).
- La etapa de diseño no se cierra sin una versión aprobada (IN-05).

## Despliegue

El protocolo completo (nube, IP elástica, Nginx, certificado y controles
CP-DES-01..03) está en la sección 8.2 del Informe N.º 3; los scripts y las
evidencias de ejecución se entregan en `evidencias/despliegue/`.
