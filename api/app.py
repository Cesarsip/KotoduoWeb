# -*- coding: utf-8 -*-
"""Kotoduo Producción - API e interfaz servidas por un solo proceso (Unidad 3).

Cumple el Informe N.º 3:
  * §8.2: la interfaz HTML/CSS/JS se sirve desde este mismo proceso Uvicorn.
  * Tablas 4 y 5: control de permisos por rol en el servidor
    (401 sin sesión o expirada, 403 sin permiso para el rol).
  * HU-06: aprobación trazable de diseños; la etapa de diseño no se cierra
    sin una versión aprobada (prueba IN-05).
  * HU-08: estado del pedido para el vendedor, con etapa y responsable,
    sin costos ni bitácora (prueba IN-06).
  * Tabla 1: alta y baja de usuarios implementada en el servidor.
  * Dos bases de datos: SQLite (estado operativo) y TinyDB (fichas de diseño).

Endurecimiento de seguridad (sección 10 del Informe 3):
  * Contraseñas con Argon2id primero y PBKDF2-SHA256 como respaldo de los
    hashes antiguos; política de clave en el alta (mínimo 10 caracteres,
    no numérica, no común y no parecida al usuario).
  * Sesión con expiración: token de acceso de 15 minutos y token de
    refresco de 8 horas, ambos aleatorios y vivos solo en memoria.
  * Bloqueo de la cuenta a los tres fallos de inicio de sesión con
    HTTP 423 Locked durante 15 minutos, entrada en la bitácora con el
    usuario y la IP, y contador a cero al acertar.
  * Límite estricto de intentos de login por IP y límite general de
    peticiones (429), cabeceras de seguridad y CORS configurable por .env.
  * Errores 400/401/403/404/409/422/423/429/500 siempre en JSON y en
    español, nunca en HTML, y sin rastro de paneles de administración
    heredados de otros frameworks (/admin/ responde 404 en JSON).

Todo el acceso a datos usa consultas parametrizadas (OWASP A03).
No hay secretos en el código: las credenciales de prueba viven solo en el
archivo de semilla, fuera del repositorio, y la configuración opcional se
carga de .env (plantilla en .env.example).
"""
import os, re, sqlite3, secrets, datetime, time, hmac, hashlib, base64, binascii
from contextlib import contextmanager
from typing import Optional, Literal
from fastapi import FastAPI, HTTPException, Depends, Request, Path, Query as QueryParam
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException
from pydantic import BaseModel, Field, field_validator, model_validator
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, InvalidHashError
from dotenv import load_dotenv
from tinydb import TinyDB, Query

# Configuración opcional desde .env sin pisar las variables del entorno
# (en el servidor las define el servicio systemd; ver .env.example).
load_dotenv()

BASE = os.path.dirname(os.path.abspath(__file__))
# Las rutas pueden sustituirse por variable de entorno. En el servidor esto
# permite correr las pruebas contra una copia (KOTODUO_DB) sin tocar la base
# real de producción; en desarrollo se usan las rutas por defecto.
DB_PATH = os.environ.get('KOTODUO_DB') or os.path.join(BASE, '..', 'datos', 'kotoduo.db')
DOC_PATH = os.environ.get('KOTODUO_DOC_DB') or os.path.join(BASE, '..', 'datos', 'documentos.json')
PROTOTIPO = os.path.join(BASE, '..', 'prototipo')


def _entero(clave: str, por_defecto: int) -> int:
    """Lee un entorno entero; si no está o no es válido, usa el defecto."""
    try:
        return int(os.environ.get(clave) or por_defecto)
    except ValueError:
        return por_defecto


# Límites y expiraciones. Los valores por defecto son los de la guía de
# endurecimiento y cada uno se puede ajustar por .env sin tocar el código.
TOKEN_MINUTOS = _entero('KOTODUO_TOKEN_MINUTOS', 15)      # token de acceso
REFRESH_HORAS = _entero('KOTODUO_REFRESH_HORAS', 8)       # token de refresco
FALLOS_MAX = _entero('KOTODUO_FALLOS_MAX', 3)             # fallos hasta bloquear
BLOQUEO_MINUTOS = _entero('KOTODUO_BLOQUEO_MINUTOS', 15)   # duración del bloqueo
LOGIN_INTENTOS = _entero('KOTODUO_LOGIN_INTENTOS', 10)     # intentos de login por IP/min
LIMITE_GENERAL = _entero('KOTODUO_LIMITE_GENERAL', 1200)   # peticiones por IP/min
CONFIA_PROXY = os.environ.get('KOTODUO_CONFIA_PROXY', '0') == '1'
CORS_ORIGENES = tuple(o.strip() for o in
                      os.environ.get('KOTODUO_CORS_ORIGENES', '').split(',') if o.strip())

# La documentación interactiva queda activa en desarrollo y se apaga en el
# servidor (KOTODUO_DOCS=0 en el servicio systemd): exponer Swagger en
# producción amplía la superficie de ataque sin beneficio operativo.
DOCS_ACTIVOS = os.environ.get('KOTODUO_DOCS', '1') != '0'
app = FastAPI(title='Kotoduo API',
              docs_url='/docs' if DOCS_ACTIVOS else None,
              redoc_url='/redoc' if DOCS_ACTIVOS else None,
              openapi_url='/openapi.json' if DOCS_ACTIVOS else None)


class BearerSeguro(HTTPBearer):
    """Cabecera Authorization obligatoria y en español (nada de mensajes
    heredados en inglés cuando falta o viene con otro esquema)."""

    def __init__(self):
        super().__init__(auto_error=False)

    async def __call__(self, request: Request):
        cred = await super().__call__(request)
        if cred is None or not cred.credentials:
            raise HTTPException(401, 'Falta la sesión: inicia de nuevo para continuar')
        return cred


bearer = BearerSeguro()

# Sesiones en memoria con expiración: decisión de i +1 trabajador registrada
# en el informe. Cada acceso vive TOKEN_MINUTOS y su refresco REFRESH_HORAS;
# al vencer se eliminan de estos diccionarios.
SESIONES: dict[str, dict] = {}    # token de acceso -> uid, expiración y su refresco
REFRESCOS: dict[str, dict] = {}   # token de refresco -> uid, expiración y acceso asociado
FALLOS: dict[str, dict] = {}      # usuario|ip -> intentos fallidos y bloqueo
INTENTOS: dict[str, list] = {}    # ip -> marcas de tiempo del login (ventana 1 min)
VENTANA: dict[str, list] = {}     # ip -> marcas de tiempo (límite general)

# Base documental: fichas de diseño de cada trabajo (TinyDB / JSON).
DOCS = TinyDB(DOC_PATH)
DISENOS = DOCS.table('disenos')

ROLES_PERMITIDOS = {
    'crear_trabajo':       {'encargado', 'administrador'},
    'cerrar_etapa':        {'operario', 'encargado', 'administrador'},
    'ver_tablero':         {'encargado', 'administrador'},
    'ver_alertas':         {'encargado', 'vendedor', 'administrador'},
    'ver_bitacora':        {'administrador'},
    'ver_trabajos':        {'encargado', 'administrador'},
    'ver_estado_pedido':   {'vendedor', 'encargado', 'administrador'},
    'ver_disenos':         {'encargado', 'vendedor', 'administrador'},
    'registrar_diseno':    {'encargado', 'administrador'},
    'decidir_diseno':      {'encargado', 'vendedor', 'administrador'},
    'administrar_usuarios': {'administrador'},
}

ESTADOS_TRABAJO = ('en_diseño', 'en_producción', 'detenido', 'terminado')


# ------------------------------------------------------------------ seguridad
ph = PasswordHasher()   # Argon2id: algoritmo de hash lento, primero siempre
PBKDF2_ITER = 390000    # respaldo para hashes antiguos en formato documentado


def hash_pbkdf2(clave: str, sal: bytes = None, iteraciones: int = PBKDF2_ITER) -> str:
    """PBKDF2-SHA256 con salt aleatorio: respaldo Argon2id (y puente de
    migración para hashes heredados). Formato: $pbkdf2-sha256$iter$sal$hash."""
    sal = sal or secrets.token_bytes(16)
    resumen = hashlib.pbkdf2_hmac('sha256', clave.encode('utf-8'), sal, iteraciones)
    b = lambda x: base64.urlsafe_b64encode(x).decode('ascii').rstrip('=')
    return f'$pbkdf2-sha256${iteraciones}${b(sal)}${b(resumen)}'


def verificar_clave(hash_guardado: str, clave: str) -> bool:
    """Argon2id primero; si el hash es PBKDF2 heredado se verifica con ese
    formato y, al acertar, se reescribe con Argon2id (migración automática
    en el próximo inicio de sesión)."""
    if hash_guardado.startswith('$argon2'):
        try:
            return ph.verify(hash_guardado, clave)
        except (VerificationError, InvalidHashError):
            return False
    if hash_guardado.startswith('$pbkdf2-sha256$'):
        partes = hash_guardado.split('$')
        if len(partes) != 5:
            return False
        try:
            iteraciones = int(partes[2])
            sal = base64.urlsafe_b64decode(partes[3] + '=' * (-len(partes[3]) % 4))
            esperado = base64.urlsafe_b64decode(partes[4] + '=' * (-len(partes[4]) % 4))
        except (ValueError, binascii.Error):
            return False
        obtenido = hashlib.pbkdf2_hmac('sha256', clave.encode('utf-8'),
                                       sal, iteraciones, dklen=len(esperado))
        return hmac.compare_digest(obtenido, esperado)
    return False


def ip_cliente(request: Request) -> str:
    """IP del cliente. Solo se confía en X-Forwarded-For cuando el servicio
    declara que hay un proxy delante (KOTODUO_CONFIA_PROXY=1 con Nginx)."""
    if CONFIA_PROXY and request.headers.get('x-forwarded-for'):
        return request.headers['x-forwarded-for'].split(',')[0].strip()
    return request.client.host if request.client else 'desconocida'


def ventana_ok(tabla: dict, clave: str, limite: int) -> bool:
    """Ventana deslizante de un minuto por clave (IP). Devuelve False y no
    registra la marca cuando el límite ya se alcanzó."""
    if limite <= 0:
        return True
    ahora = time.time()
    marcas = [m for m in tabla.get(clave, []) if m > ahora - 60]
    if len(marcas) >= limite:
        tabla[clave] = marcas
        return False
    marcas.append(ahora)
    tabla[clave] = marcas
    if len(tabla) > 500:            # poda de direcciones ya vencidas
        for k in list(tabla):
            viejas = [m for m in tabla[k] if m > ahora - 60]
            if viejas:
                tabla[k] = viejas
            else:
                del tabla[k]
    return True


def limpiar_expiradas():
    """Elimina tokens vencidos para que los diccionarios no crezcan sin
    control mientras el proceso está vivo."""
    ahora = time.time()
    for tabla in (SESIONES, REFRESCOS):
        for k in [k for k, v in tabla.items() if v['exp'] < ahora]:
            del tabla[k]


@contextmanager
def transaccion(db):
    """Escritura explícita sobre SQLite: BEGIN IMMEDIATE serializa la
    operación completa (equivalente al SELECT ... FOR UPDATE de otros
    motores) y cualquier fallo la revierte entera con ROLLBACK."""
    db.execute('BEGIN IMMEDIATE')
    try:
        yield
        db.execute('COMMIT')
    except Exception:
        db.execute('ROLLBACK')
        raise


# Contraseñas rechazadas en el alta (lista corta de uso común).
CLAVES_COMUNES = {
    '12345678901', '123456789123', 'contrasena123', 'contrasena1234',
    'password123', 'password1234', 'qwertyuiop', 'qwertyuiop123',
    'admin123456', 'administrator', 'kotoduo2026', 'kotoduo1234',
    'usuario12345', 'clave123456', 'abc12345678', 'iloveyou123',
}

EXTENSIONES_ARCHIVO = ('.svg', '.png', '.pdf', '.jpg', '.jpeg')


def ruta_archivo(v: str) -> str:
    """Validación de la referencia de archivo de un diseño.

    El alcance actual solo guarda la ruta (no se suben binarios, tal como
    describen las tablas del informe): aquí se aplica la parte que sí toca
    —extensión admitida, sin traversal y sin caracteres especiales—. Si en
    el futuro se añade la carga real, el endpoint debe además limitar el
    cuerpo a 5 MB, leer el MIME real del archivo, guardarlo con nombre
    uuid4 y registrar su SHA-256 en la base.
    """
    if '..' in v or v.startswith('/') or '\\' in v:
        raise ValueError('la ruta del archivo no puede contener .. ni ser absoluta')
    if not re.fullmatch(r'[A-Za-z0-9._\-/]+', v):
        raise ValueError('la ruta del archivo solo admite letras, números, punto, guion y barra')
    if not v.lower().endswith(EXTENSIONES_ARCHIVO):
        raise ValueError('formato no admitido: usa svg, png, pdf o jpg')
    return v


# ------------------------------------------------------------------ base de datos
def get_db():
    # check_same_thread=False: FastAPI ejecuta los endpoints en un pool de
    # hilos y el cierre puede caer en otro hilo; la conexión es por petición
    # y no se comparte entre ellas.
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    try:
        yield conn
    finally:
        conn.close()


def usuario_actual(cred: HTTPAuthorizationCredentials = Depends(bearer), db=Depends(get_db)):
    entrada = SESIONES.get(cred.credentials)
    if entrada is None or entrada['exp'] < time.time():
        SESIONES.pop(cred.credentials, None)
        raise HTTPException(401, 'Sesión inválida o expirada')
    row = db.execute('SELECT id, usuario, nombre, rol, activo FROM usuarios WHERE id=?',
                     (entrada['uid'],)).fetchone()
    if not row or not row['activo']:
        raise HTTPException(401, 'Usuario inexistente o inactivo')
    return dict(row)


def requiere(accion: str):
    def dep(user=Depends(usuario_actual)):
        if user['rol'] not in ROLES_PERMITIDOS[accion]:
            raise HTTPException(403, f'El rol {user["rol"]} no puede: {accion}')
        return user
    return dep


def bitacora(db, user, accion, entidad, entidad_id, anterior=None, posterior=None):
    db.execute('''INSERT INTO bitacora (usuario_id, accion, entidad, entidad_id,
                                        valor_anterior, valor_posterior)
                  VALUES (?,?,?,?,?,?)''',
               (user['id'], accion, entidad, entidad_id, anterior, posterior))


def trabajo_o_404(db, codigo: str):
    fila = db.execute('SELECT * FROM trabajos WHERE codigo=?', (codigo,)).fetchone()
    if not fila:
        raise HTTPException(404, 'Trabajo inexistente')
    return fila


# ------------------------------------------------------------------ modelos
class Login(BaseModel):
    usuario: str = Field(min_length=3, max_length=20, pattern=r'^[a-z0-9._-]+$')
    password: str = Field(min_length=8, max_length=72)


class TrabajoIn(BaseModel):
    codigo: str = Field(pattern=r'^KTO-2026-\d{3}$')
    tipo_trabajo: str
    cliente_etiqueta: str = Field(min_length=2, max_length=80)
    pedido_ref: Optional[str] = Field(default=None, max_length=30)
    unidades: int = Field(gt=0, le=5000)
    medidas: str = Field(min_length=3, max_length=200)
    fecha_compromiso: Optional[str] = Field(default=None, pattern=r'^\d{4}-\d{2}-\d{2}$')

    @field_validator('medidas', 'cliente_etiqueta')
    @classmethod
    def sin_html(cls, v: str):
        if '<' in v or '>' in v:
            raise ValueError('no se aceptan etiquetas HTML en los campos de texto')
        return v


class VarianteIn(BaseModel):
    nombre: str = Field(min_length=2, max_length=40)
    medidas: str = Field(min_length=3, max_length=40)
    archivo: str = Field(min_length=3, max_length=80)

    @field_validator('archivo')
    @classmethod
    def ruta_admitida(cls, v: str):
        return ruta_archivo(v)


class DisenoIn(BaseModel):
    """Nueva versión de diseño enviada a aprobación (HU-06)."""
    archivo: str = Field(min_length=3, max_length=120)
    formato: Literal['svg', 'png', 'pdf', 'jpg'] = 'svg'
    paleta: list[str] = Field(default_factory=list, max_length=10)
    variantes: list[VarianteIn] = Field(default_factory=list, max_length=10)
    observaciones: list[str] = Field(default_factory=list, max_length=10)

    @field_validator('archivo')
    @classmethod
    def ruta_admitida(cls, v: str):
        return ruta_archivo(v)

    @field_validator('observaciones')
    @classmethod
    def sin_html(cls, v):
        if '<' in v or '>' in v:
            raise ValueError('no se aceptan etiquetas HTML en los campos de texto')
        return v


class DecisionIn(BaseModel):
    """Decisión sobre una versión de diseño: aprobada o rechazada (HU-06)."""
    estado: Literal['aprobado', 'rechazado']
    comentarios: Optional[str] = Field(default=None, max_length=300)


class UsuarioIn(BaseModel):
    usuario: str = Field(min_length=3, max_length=20, pattern=r'^[a-z0-9._-]+$')
    nombre: str = Field(min_length=2, max_length=60)
    password: str = Field(min_length=10, max_length=72)
    rol: Literal['operario', 'encargado', 'vendedor', 'administrador']

    @field_validator('nombre')
    @classmethod
    def sin_html(cls, v: str):
        if '<' in v or '>' in v:
            raise ValueError('no se aceptan etiquetas HTML en los campos de texto')
        return v

    @model_validator(mode='after')
    def clave_fuerte(self):
        """Política de contraseña en el alta (endurecimiento): mínimo diez
        caracteres, no numérica, no común y no parecida al nombre de usuario."""
        clave = self.password
        if clave.isdigit():
            raise ValueError('la contraseña no puede ser solo numérica')
        if clave.lower() in CLAVES_COMUNES:
            raise ValueError('la contraseña es demasiado común: elige otra')
        usuario = self.usuario.lower()
        if usuario in clave.lower() or clave.lower() in usuario:
            raise ValueError('la contraseña no debe parecerse al nombre de usuario')
        return self


class UsuarioPatch(BaseModel):
    activo: Optional[bool] = None
    rol: Optional[Literal['operario', 'encargado', 'vendedor', 'administrador']] = None

    @model_validator(mode='after')
    def al_menos_un_campo(self):
        if self.activo is None and self.rol is None:
            raise ValueError('indica al menos un campo: activo o rol')
        return self


# ------------------------------------------------------------------ autenticación
class RefreshIn(BaseModel):
    refresh_token: str = Field(min_length=20, max_length=200)


def fallo_conteo(db, clave_fallo, row, ip):
    """Suma un fallo de inicio de sesión. Aplica dos controles en capas:
    el límite estricto de fallos por IP (LOGIN_INTENTOS por minuto, 429) y
    el bloqueo de la cuenta a los FALLOS_MAX fallos (423), dejando constancia
    en la bitácora con el usuario y la IP cuando la cuenta existe (la
    bitácora exige usuario_id, por eso los usuarios inexistentes solo se
    cuentan)."""
    if not ventana_ok(INTENTOS, ip, LOGIN_INTENTOS):
        raise HTTPException(429, 'Demasiados intentos fallidos de inicio de sesión '
                                 'desde esta IP; espera un minuto y vuelve a intentarlo')
    usuario = clave_fallo.split('|', 1)[0]
    entrada = FALLOS.setdefault(clave_fallo, {'n': 0, 'hasta': 0.0})
    entrada['n'] += 1
    if entrada['n'] >= FALLOS_MAX:
        entrada['hasta'] = time.time() + BLOQUEO_MINUTOS * 60
        if row:
            bitacora(db, {'id': row['id']}, 'login_bloqueado', 'usuarios', row['id'],
                     f'{entrada["n"]} fallos consecutivos desde {ip}',
                     f'bloqueado {BLOQUEO_MINUTOS} minutos')
            db.commit()
        raise HTTPException(
            423, f'Cuenta bloqueada {BLOQUEO_MINUTOS} minutos tras {FALLOS_MAX} '
                 f'intentos fallidos de {usuario}. Si no fuiste tú, avisa al administrador')


def emitir_sesion(row) -> tuple[str, str]:
    """Crea el par de tokens: acceso corto (TOKEN_MINUTOS) y refresco largo
    (REFRESH_HORAS), ambos aleatorios y vivos solo en memoria."""
    limpiar_expiradas()
    ahora = time.time()
    token = secrets.token_urlsafe(24)
    refresh = secrets.token_urlsafe(32)
    SESIONES[token] = {'uid': row['id'], 'exp': ahora + TOKEN_MINUTOS * 60,
                       'refresh': refresh}
    REFRESCOS[refresh] = {'uid': row['id'], 'exp': ahora + REFRESH_HORAS * 3600,
                          'token': token}
    return token, refresh


@app.post('/auth/login')
def login(body: Login, request: Request, db=Depends(get_db)):
    ip = ip_cliente(request)
    clave_fallo = f'{body.usuario}|{ip}'

    # Bloqueo a los tres fallos durante BLOQUEO_MINUTOS (HTTP 423 Locked).
    # La clave incluye la IP: un tercero no puede dejar bloqueada a una
    # persona real desde otra red, y el límite por IP cubre el resto.
    fallo = FALLOS.get(clave_fallo)
    if fallo and fallo['hasta'] > time.time():
        restan = int((fallo['hasta'] - time.time()) / 60) + 1
        raise HTTPException(
            423, f'Cuenta bloqueada tras {FALLOS_MAX} intentos fallidos de {body.usuario}; '
                 f'vuelve a intentarlo en {restan} minuto(s). Si no fuiste tú, avisa al administrador')
    if fallo and fallo['hasta']:
        FALLOS.pop(clave_fallo)   # venció un bloqueo anterior: contador a cero

    row = db.execute('SELECT id, usuario, nombre, rol, password_hash, activo '
                     'FROM usuarios WHERE usuario=?', (body.usuario,)).fetchone()
    if not row or not row['activo']:
        fallo_conteo(db, clave_fallo, row, ip)
        raise HTTPException(401, 'Credenciales inválidas')

    if not verificar_clave(row['password_hash'], body.password):
        fallo_conteo(db, clave_fallo, row, ip)
        raise HTTPException(401, 'Credenciales inválidas')

    # Acertó: contador de fallos a cero y hash migrado si es antiguo.
    FALLOS.pop(clave_fallo, None)
    antiguo = not row['password_hash'].startswith('$argon2')
    if antiguo or ph.check_needs_rehash(row['password_hash']):
        db.execute('UPDATE usuarios SET password_hash=? WHERE id=?',
                   (ph.hash(body.password), row['id']))
        db.commit()

    token, refresh = emitir_sesion(row)
    return {'token': token, 'refresh_token': refresh,
            'expira_en': TOKEN_MINUTOS * 60,
            'usuario': row['usuario'], 'nombre': row['nombre'], 'rol': row['rol']}


@app.post('/auth/refresh')
def refrescar_sesion(body: RefreshIn, request: Request, db=Depends(get_db)):
    """Emite un token de acceso nuevo con el refresco vigente (8 horas)."""
    ip = ip_cliente(request)
    if not ventana_ok(INTENTOS, f'refresh|{ip}', LOGIN_INTENTOS):
        raise HTTPException(429, 'Demasiadas renovaciones de sesión desde esta IP; '
                                 'espera un minuto y vuelve a intentarlo')
    entrada = REFRESCOS.get(body.refresh_token)
    if entrada is None or entrada['exp'] < time.time():
        REFRESCOS.pop(body.refresh_token, None)
        raise HTTPException(401, 'Sesión expirada: vuelve a iniciar sesión')
    row = db.execute('SELECT id, usuario, nombre, rol, activo FROM usuarios WHERE id=?',
                     (entrada['uid'],)).fetchone()
    if not row or not row['activo']:
        raise HTTPException(401, 'Usuario inexistente o inactivo')
    token = secrets.token_urlsafe(24)
    SESIONES[token] = {'uid': row['id'], 'exp': time.time() + TOKEN_MINUTOS * 60,
                       'refresh': body.refresh_token}
    return {'token': token, 'expira_en': TOKEN_MINUTOS * 60,
            'usuario': row['usuario'], 'nombre': row['nombre'], 'rol': row['rol']}


@app.post('/auth/logout')
def cerrar_sesion(cred: HTTPAuthorizationCredentials = Depends(bearer)):
    """Cierra la sesión en el servidor: retira el acceso y su refresco."""
    entrada = SESIONES.pop(cred.credentials, None)
    if entrada:
        REFRESCOS.pop(entrada.get('refresh'), None)
    return {'mensaje': 'Sesión cerrada'}


# ------------------------------------------------------------------ HU-01 / HU-02
@app.get('/trabajos/siguiente')
def siguiente_actividad(db=Depends(get_db), user=Depends(requiere('cerrar_etapa'))):
    fila = db.execute(
        '''SELECT t.codigo, t.cliente_etiqueta, t.medidas, t.unidades, t.fecha_compromiso,
                  ed.nombre AS etapa, ed.area, ed.orden,
                  (SELECT COUNT(*) FROM etapas_trabajo x WHERE x.trabajo_id=t.id)
                      AS total_etapas,
                  et.id AS etapa_trabajo_id
           FROM etapas_trabajo et
           JOIN trabajos t ON t.id = et.trabajo_id
           JOIN etapas_definicion ed ON ed.id = et.etapa_def_id
           WHERE et.estado IN ('pendiente','en_curso')
             AND (et.responsable_id IS NULL OR et.responsable_id = ?)
           ORDER BY t.fecha_compromiso, ed.orden LIMIT 1''', (user['id'],)).fetchone()
    return dict(fila) if fila else {'mensaje': 'Sin etapas abiertas'}


@app.post('/etapas/{etapa_id}/cerrar')
def cerrar_etapa(etapa_id: int = Path(ge=1, le=10_000_000),
                 db=Depends(get_db), user=Depends(requiere('cerrar_etapa'))):
    fila = db.execute(
        '''SELECT et.id, et.estado, t.id AS trabajo_id, t.codigo, t.estado_general,
                  ed.area, ed.orden
           FROM etapas_trabajo et
           JOIN trabajos t ON t.id = et.trabajo_id
           JOIN etapas_definicion ed ON ed.id = et.etapa_def_id
           WHERE et.id=?''', (etapa_id,)).fetchone()
    if not fila:
        raise HTTPException(404, 'Etapa inexistente')
    if fila['estado'] == 'cerrada':
        raise HTTPException(409, 'La etapa ya está cerrada')

    # HU-06 / IN-05: la etapa de diseño no se cierra sin versión aprobada.
    if fila['area'] == 'diseño':
        aprobada = db.execute(
            "SELECT 1 FROM aprobaciones_diseno WHERE trabajo_id=? AND estado='aprobado' LIMIT 1",
            (fila['trabajo_id'],)).fetchone()
        if not aprobada:
            raise HTTPException(
                409, 'La etapa de diseño no se cierra sin una versión aprobada (HU-06)')

    if user['rol'] == 'operario':
        resp = db.execute('SELECT responsable_id FROM etapas_trabajo WHERE id=?',
                          (etapa_id,)).fetchone()
        if resp['responsable_id'] not in (None, user['id']):
            raise HTTPException(403, 'La etapa está asignada a otra persona')

    # Escritura atómica (BEGIN IMMEDIATE): el cierre, la bitácora y el cambio
    # de estado del trabajo se aplican juntos o no se aplica ninguno.
    with transaccion(db):
        db.execute('''UPDATE etapas_trabajo SET estado='cerrada', responsable_id=?,
                      fecha_cierre=datetime('now') WHERE id=?''', (user['id'], etapa_id))
        bitacora(db, user, 'cerrar_etapa', 'etapas_trabajo', etapa_id, fila['estado'], 'cerrada')

        # Transiciones del estado general del trabajo (HU-03 / HU-06).
        abiertas = db.execute("SELECT COUNT(*) AS n FROM etapas_trabajo "
                              "WHERE trabajo_id=? AND estado<>'cerrada'",
                              (fila['trabajo_id'],)).fetchone()['n']
        nuevo = None
        if abiertas == 0:
            nuevo = 'terminado'
        elif fila['area'] == 'diseño' and fila['estado_general'] == 'en_diseño':
            nuevo = 'en_producción'
        if nuevo and nuevo != fila['estado_general']:
            db.execute('UPDATE trabajos SET estado_general=? WHERE id=?',
                       (nuevo, fila['trabajo_id']))
            bitacora(db, user, 'cambiar_estado', 'trabajos', fila['trabajo_id'],
                     fila['estado_general'], nuevo)
    return {'etapa': etapa_id, 'trabajo': fila['codigo'], 'estado': 'cerrada',
            'estado_trabajo': nuevo or fila['estado_general']}


# ------------------------------------------------------------------ HU-03
@app.post('/trabajos', status_code=201)
def crear_trabajo(body: TrabajoIn, db=Depends(get_db), user=Depends(requiere('crear_trabajo'))):
    # Transacción explícita: el trabajo, sus etapas, la versión de diseño
    # pendiente y la bitácora entran juntos o no entra ninguno.
    with transaccion(db):
        try:
            cur = db.execute(
                '''INSERT INTO trabajos (codigo, tipo_trabajo, cliente_etiqueta, pedido_ref,
                                         unidades, medidas, fecha_compromiso, creado_por,
                                         estado_general)
                   VALUES (?,?,?,?,?,?,?,?,'en_diseño')''',
                (body.codigo, body.tipo_trabajo, body.cliente_etiqueta, body.pedido_ref,
                 body.unidades, body.medidas, body.fecha_compromiso, user['id']))
        except sqlite3.IntegrityError:
            raise HTTPException(409, 'Código de trabajo duplicado o tipo no válido')
        db.execute(
            '''INSERT INTO etapas_trabajo (trabajo_id, etapa_def_id, estado)
               SELECT ?, id, 'pendiente' FROM etapas_definicion WHERE tipo_trabajo=? ORDER BY orden''',
            (cur.lastrowid, body.tipo_trabajo))
        # Toda versión de diseño nace pendiente de aprobación en ambas bases.
        version = 1
        db.execute('''INSERT INTO aprobaciones_diseno (trabajo_id, version, estado)
                      VALUES (?,?, 'pendiente')''', (cur.lastrowid, version))
        bitacora(db, user, 'crear', 'trabajos', cur.lastrowid, None, body.codigo)
    DISENOS.insert({
        'trabajo_codigo': body.codigo,
        'version': version,
        'archivo': f'diseños/{body.codigo}/v1_borrador.{body.tipo_trabajo}',
        'formato': 'svg',
        'paleta': [],
        'variantes': [],
        'observaciones': ['Borrador creado con el trabajo; espera la aprobación del cliente'],
        'aprobado': False,
        'decidido_por': None,
        'fecha': datetime.datetime.now().strftime('%Y-%m-%d %H:%M'),
    })
    return {'id': cur.lastrowid, 'codigo': body.codigo, 'estado_general': 'en_diseño'}


# ------------------------------------------------------------------ lectura de trabajos
@app.get('/trabajos')
def listar_trabajos(estado: Optional[Literal['en_diseño', 'en_producción',
                                             'detenido', 'terminado']] = None,
                    db=Depends(get_db), user=Depends(requiere('ver_trabajos'))):
    """Lista de trabajos con su siguiente etapa abierta (tablero, HU-05)."""
    sql = '''SELECT id, codigo, tipo_trabajo, cliente_etiqueta, pedido_ref, unidades,
                    medidas, estado_general, fecha_compromiso, creado_en
             FROM trabajos'''
    params: tuple = ()
    if estado:
        sql += ' WHERE estado_general=?'
        params = (estado,)
    sql += ' ORDER BY fecha_compromiso, codigo'
    trabajos = [dict(f) for f in db.execute(sql, params).fetchall()]

    abiertas = db.execute(
        '''SELECT et.id, et.trabajo_id, et.estado, ed.nombre, ed.orden,
                  u.nombre AS responsable
           FROM etapas_trabajo et
           JOIN etapas_definicion ed ON ed.id=et.etapa_def_id
           LEFT JOIN usuarios u ON u.id=et.responsable_id
           WHERE et.estado IN ('pendiente','en_curso','detenida')
           ORDER BY ed.orden''').fetchall()
    primera: dict[int, dict] = {}
    for a in abiertas:
        primera.setdefault(a['trabajo_id'], dict(a))

    for t in trabajos:
        et = primera.get(t['id'])
        t['etapa_actual'] = et['nombre'] if et else None
        t['estado_etapa'] = et['estado'] if et else None
        t['responsable'] = et['responsable'] if et else None
        t['etapa_trabajo_id'] = et['id'] if et else None
    return trabajos


# ------------------------------------------------------------------ HU-08 (IN-06)
@app.get('/trabajos/{codigo}/estado')
def estado_pedido(codigo: str = Path(pattern=r'^KTO-\d{4}-\d{3}$'),
                  db=Depends(get_db), user=Depends(requiere('ver_estado_pedido'))):
    """Ficha de estado para el vendedor: etapa y responsable, sin costos
    ni bitácora (IN-06)."""
    t = trabajo_o_404(db, codigo)
    etapa = db.execute(
        '''SELECT ed.nombre AS etapa, ed.area, ed.orden, et.estado,
                  u.nombre AS responsable
           FROM etapas_trabajo et
           JOIN etapas_definicion ed ON ed.id=et.etapa_def_id
           LEFT JOIN usuarios u ON u.id=et.responsable_id
           WHERE et.trabajo_id=? AND et.estado IN ('pendiente','en_curso','detenida')
           ORDER BY ed.orden LIMIT 1''', (t['id'],)).fetchone()
    cont = db.execute('''SELECT SUM(estado='cerrada') AS cerradas, COUNT(*) AS total
                         FROM etapas_trabajo WHERE trabajo_id=?''',
                      (t['id'],)).fetchone()
    dis = db.execute('''SELECT version, estado FROM aprobaciones_diseno
                        WHERE trabajo_id=? ORDER BY version DESC LIMIT 1''',
                     (t['id'],)).fetchone()
    return {
        'codigo': t['codigo'],
        'tipo_trabajo': t['tipo_trabajo'],
        'cliente_etiqueta': t['cliente_etiqueta'],
        'pedido_ref': t['pedido_ref'],
        'estado_general': t['estado_general'],
        'etapa_actual': etapa['etapa'] if etapa else None,
        'area': etapa['area'] if etapa else None,
        'estado_etapa': etapa['estado'] if etapa else None,
        'responsable': etapa['responsable'] if etapa else 'Sin asignar',
        'etapas_cerradas': cont['cerradas'] or 0,
        'total_etapas': cont['total'],
        'fecha_compromiso': t['fecha_compromiso'],
        'unidades': t['unidades'],
        'medidas': t['medidas'],
        'diseno_version': dis['version'] if dis else None,
        'diseno': dis['estado'] if dis else 'sin_version',
    }


# ------------------------------------------------------------------ HU-06 (IN-05)
@app.get('/trabajos/{codigo}/disenos')
def listar_disenos(codigo: str = Path(pattern=r'^KTO-\d{4}-\d{3}$'),
                   db=Depends(get_db), user=Depends(requiere('ver_disenos'))):
    """Versiones de diseño: control en SQLite + ficha gráfica en TinyDB."""
    t = trabajo_o_404(db, codigo)
    filas = db.execute(
        '''SELECT ad.version, ad.estado, ad.comentarios, ad.fecha,
                  u.nombre AS decidido_por
           FROM aprobaciones_diseno ad
           LEFT JOIN usuarios u ON u.id=ad.decidido_por
           WHERE ad.trabajo_id=? ORDER BY ad.version''', (t['id'],)).fetchall()
    q = Query()
    fichas = {d['version']: d for d in DISENOS.search(q.trabajo_codigo == codigo)}
    out = []
    for f in filas:
        item = dict(f)
        item['codigo'] = codigo
        ficha = fichas.get(f['version'])
        item['archivo'] = ficha['archivo'] if ficha else None
        item['formato'] = ficha['formato'] if ficha else None
        item['paleta'] = ficha['paleta'] if ficha else []
        item['variantes'] = ficha['variantes'] if ficha else []
        item['observaciones'] = ficha['observaciones'] if ficha else []
        out.append(item)
    return out


@app.post('/trabajos/{codigo}/disenos', status_code=201)
def nueva_version_diseno(body: DisenoIn,
                         codigo: str = Path(pattern=r'^KTO-\d{4}-\d{3}$'),
                         db=Depends(get_db), user=Depends(requiere('registrar_diseno'))):
    """Registra una nueva versión de diseño y la deja pendiente de decisión."""
    t = trabajo_o_404(db, codigo)
    ultima = db.execute('SELECT MAX(version) AS v FROM aprobaciones_diseno '
                        'WHERE trabajo_id=?', (t['id'],)).fetchone()['v'] or 0
    version = ultima + 1
    with transaccion(db):
        try:
            db.execute('''INSERT INTO aprobaciones_diseno (trabajo_id, version, estado)
                          VALUES (?,?, 'pendiente')''', (t['id'], version))
        except sqlite3.IntegrityError:
            raise HTTPException(409, 'La versión de diseño ya existe')
        bitacora(db, user, 'crear_version_diseno', 'aprobaciones_diseno',
                 t['id'] * 100 + version, None, f'{codigo} v{version} pendiente')
    DISENOS.insert({
        'trabajo_codigo': codigo,
        'version': version,
        'archivo': body.archivo,
        'formato': body.formato,
        'paleta': list(body.paleta),
        'variantes': [v.model_dump() for v in body.variantes],
        'observaciones': list(body.observaciones),
        'aprobado': False,
        'decidido_por': None,
        'fecha': datetime.datetime.now().strftime('%Y-%m-%d %H:%M'),
    })
    return {'codigo': codigo, 'version': version, 'estado': 'pendiente'}


@app.post('/trabajos/{codigo}/disenos/{version}/decision')
def decidir_diseno(body: DecisionIn,
                   codigo: str = Path(pattern=r'^KTO-\d{4}-\d{3}$'),
                   version: int = Path(ge=1, le=999),
                   db=Depends(get_db), user=Depends(requiere('decidir_diseno'))):
    """Aprueba o rechaza una versión de diseño (HU-06 / IN-05)."""
    t = trabajo_o_404(db, codigo)
    fila = db.execute('SELECT * FROM aprobaciones_diseno WHERE trabajo_id=? AND version=?',
                      (t['id'], version)).fetchone()
    if not fila:
        raise HTTPException(404, 'Versión de diseño inexistente')
    if fila['estado'] != 'pendiente':
        raise HTTPException(409, 'La versión de diseño ya fue decidida')

    # Decisión y transiciones de estado en una sola transacción: la versión,
    # la bitácora y el estado del trabajo cambian juntos o no cambia nada.
    with transaccion(db):
        db.execute('''UPDATE aprobaciones_diseno
                      SET estado=?, decidido_por=?, comentarios=?, fecha=datetime('now')
                      WHERE id=?''', (body.estado, user['id'], body.comentarios, fila['id']))
        bitacora(db, user, 'cambiar_estado', 'aprobaciones_diseno', fila['id'],
                 fila['estado'], body.estado)

        # Rechazo: el trabajo queda detenido hasta que haya una versión aprobada.
        # Aprobación: si el diseño sigue abierto, vuelve a estar en diseño.
        if body.estado == 'rechazado' and t['estado_general'] in ('en_diseño', 'en_producción'):
            db.execute("UPDATE trabajos SET estado_general='detenido' WHERE id=?", (t['id'],))
            bitacora(db, user, 'cambiar_estado', 'trabajos', t['id'],
                     t['estado_general'], 'detenido')
        elif body.estado == 'aprobado' and t['estado_general'] == 'detenido':
            diseno_abierto = db.execute(
                '''SELECT 1 FROM etapas_trabajo et
                   JOIN etapas_definicion ed ON ed.id=et.etapa_def_id
                   WHERE et.trabajo_id=? AND ed.area='diseño' AND et.estado<>'cerrada'
                   LIMIT 1''', (t['id'],)).fetchone()
            if diseno_abierto:
                db.execute("UPDATE trabajos SET estado_general='en_diseño' WHERE id=?", (t['id'],))
                bitacora(db, user, 'cambiar_estado', 'trabajos', t['id'],
                         t['estado_general'], 'en_diseño')

    # Se mantiene sincronizada la ficha documental (TinyDB) tras el commit.
    q = Query()
    DISENOS.update({'aprobado': body.estado == 'aprobado',
                    'decidido_por': user['usuario'],
                    'fecha': datetime.datetime.now().strftime('%Y-%m-%d %H:%M')},
                   (q.trabajo_codigo == codigo) & (q.version == version))
    return {'codigo': codigo, 'version': version, 'estado': body.estado}


# ------------------------------------------------------------------ HU-05 / HU-04
@app.get('/tablero')
def tablero(db=Depends(get_db), user=Depends(requiere('ver_tablero'))):
    filas = db.execute('''SELECT estado_general, COUNT(*) AS n FROM trabajos
                          GROUP BY estado_general''').fetchall()
    return {f['estado_general']: f['n'] for f in filas}


@app.get('/insumos/alertas')
def alertas(db=Depends(get_db), user=Depends(requiere('ver_alertas'))):
    filas = db.execute('''SELECT i.nombre, i.stock_actual, i.umbral_minimo
                          FROM insumos i WHERE i.stock_actual < i.umbral_minimo''').fetchall()
    return [dict(f) for f in filas]


# ------------------------------------------------------------------ HU-07
@app.get('/bitacora')
def bitacora_lista(entidad: Optional[str] = QueryParam(default=None, max_length=40,
                                                       pattern=r'^[a-z_]+$'),
                   entidad_id: Optional[int] = QueryParam(default=None, ge=1),
                   db=Depends(get_db), user=Depends(requiere('ver_bitacora'))):
    """Bitácora inmutable: de una entidad concreta o las últimas 20 entradas."""
    if entidad is None and entidad_id is None:
        filas = db.execute(
            '''SELECT b.fecha, u.nombre, b.accion, b.entidad, b.entidad_id,
                      b.valor_anterior, b.valor_posterior
               FROM bitacora b JOIN usuarios u ON u.id=b.usuario_id
               ORDER BY b.fecha DESC, b.id DESC LIMIT 20''').fetchall()
        return [dict(f) for f in filas]
    if entidad is None or entidad_id is None:
        raise HTTPException(422, 'Indica entidad y entidad_id, o ninguno de los dos')
    filas = db.execute(
        '''SELECT b.fecha, u.nombre, b.accion, b.entidad, b.entidad_id,
                  b.valor_anterior, b.valor_posterior
           FROM bitacora b JOIN usuarios u ON u.id=b.usuario_id
           WHERE b.entidad=? AND b.entidad_id=? ORDER BY b.fecha''',
        (entidad, entidad_id)).fetchall()
    return [dict(f) for f in filas]


# ------------------------------------------------------------------ Tabla 1: usuarios
@app.get('/usuarios')
def listar_usuarios(db=Depends(get_db), user=Depends(requiere('administrar_usuarios'))):
    filas = db.execute('''SELECT id, usuario, nombre, rol, activo, creado_en
                          FROM usuarios ORDER BY usuario''').fetchall()
    return [dict(f) for f in filas]


@app.post('/usuarios', status_code=201)
def crear_usuario(body: UsuarioIn, db=Depends(get_db),
                  user=Depends(requiere('administrar_usuarios'))):
    existe = db.execute('SELECT 1 FROM usuarios WHERE usuario=?', (body.usuario,)).fetchone()
    if existe:
        raise HTTPException(409, 'El usuario ya existe')
    with transaccion(db):
        try:
            cur = db.execute('INSERT INTO usuarios (usuario, nombre, password_hash, rol) '
                             'VALUES (?,?,?,?)',
                             (body.usuario, body.nombre, ph.hash(body.password), body.rol))
        except sqlite3.IntegrityError:
            raise HTTPException(409, 'Usuario duplicado o rol no válido')
        bitacora(db, user, 'alta_usuario', 'usuarios', cur.lastrowid, None, body.usuario)
    # Nunca se devuelve password_hash (serialización de solo salida).
    return {'id': cur.lastrowid, 'usuario': body.usuario, 'nombre': body.nombre,
            'rol': body.rol, 'activo': 1}


@app.patch('/usuarios/{usuario_id}')
def modificar_usuario(body: UsuarioPatch,
                      usuario_id: int = Path(ge=1, le=10_000_000),
                      db=Depends(get_db), user=Depends(requiere('administrar_usuarios'))):
    fila = db.execute('SELECT * FROM usuarios WHERE id=?', (usuario_id,)).fetchone()
    if not fila:
        raise HTTPException(404, 'Usuario inexistente')
    if fila['id'] == user['id'] and body.activo is False:
        raise HTTPException(409, 'No puedes desactivar tu propia cuenta')
    if fila['id'] == user['id'] and body.rol and body.rol != fila['rol']:
        raise HTTPException(409, 'No puedes cambiar tu propio rol')

    with transaccion(db):
        if body.activo is not None and body.activo != bool(fila['activo']):
            # Baja lógica: la fila se conserva con activo=0 para no perder
            # el historial ni romper la bitácora (nunca se borra la cuenta).
            db.execute('UPDATE usuarios SET activo=? WHERE id=?',
                       (1 if body.activo else 0, usuario_id))
            bitacora(db, user, 'baja_usuario' if not body.activo else 'activar_usuario',
                     'usuarios', usuario_id, str(fila['activo']), str(int(body.activo)))
        if body.rol is not None and body.rol != fila['rol']:
            try:
                db.execute('UPDATE usuarios SET rol=? WHERE id=?', (body.rol, usuario_id))
            except sqlite3.IntegrityError:
                raise HTTPException(422, 'Rol no válido')
            bitacora(db, user, 'cambiar_rol', 'usuarios', usuario_id, fila['rol'], body.rol)
    actualizado = db.execute('SELECT id, usuario, nombre, rol, activo FROM usuarios '
                             'WHERE id=?', (usuario_id,)).fetchone()
    return dict(actualizado)


# ------------------------------------------------------------------ operación
@app.get('/health')
def health(db=Depends(get_db)):
    """Sonda de estado para Nginx y el monitoreo: comprueba que la base
    responde y no expone ningún dato."""
    db.execute('SELECT 1').fetchone()
    return {'estado': 'ok'}


# ------------------------------------------------------------------ errores en JSON
def mensaje_validacion(err: dict) -> str:
    """Pasa los mensajes técnicos de validación al español: la interfaz
    muestra tal cual lo que sale de aquí (422 en JSON, nunca en HTML)."""
    msg = str(err.get('msg', ''))
    for viejo in ('Value error, ', 'value_error, '):
        msg = msg.replace(viejo, '')
    loc = err.get('loc', ())
    campo = '.'.join(str(x) for x in loc[1:]) if len(loc) > 1 else ''
    patrones = (
        (r'^Field required$', 'campo obligatorio'),
        (r'^String should have at least (\d+) characters$', r'debe tener al menos \1 caracteres'),
        (r'^String should have at most (\d+) characters$', r'debe tener como máximo \1 caracteres'),
        (r'^String should match pattern .*$', 'no cumple el formato esperado'),
        (r'^Input should be greater than (\d+)$', r'debe ser mayor que \1'),
        (r'^Input should be less than or equal to (\d+)$', r'debe ser menor o igual que \1'),
        (r'^Input should be a valid string$', 'debe ser texto'),
        (r'^Input should be a valid integer$', 'debe ser un número entero'),
        (r'^Input should be a valid boolean$', 'debe ser verdadero o falso'),
        (r'^Input should be a valid datetime.*$', 'fecha no válida'),
        (r'^Input is not a valid integer$', 'debe ser un número entero'),
        (r'^Input is not a valid datetime.*$', 'fecha no válida'),
        (r'^Input should be .*$', 'valor no admitido'),
        (r'^Input is not .*$', 'valor no válido'),
    )
    for patron, salida in patrones:
        nuevo = re.sub(patron, salida, msg)
        if nuevo != msg:
            msg = nuevo
            break
    return f'{campo}: {msg}' if campo else msg


@app.exception_handler(HTTPException)
async def error_http(request: Request, exc: HTTPException):
    """Todo error HTTP sale en JSON con el mensaje en español:
    jamás una página HTML de error (ni el 404 de un panel /admin/)."""
    return JSONResponse({'detail': exc.detail}, status_code=exc.status_code,
                        headers=getattr(exc, 'headers', None))


@app.exception_handler(RequestValidationError)
async def error_validacion(request: Request, exc: RequestValidationError):
    detalle = []
    for err in exc.errors():
        detalle.append({'msg': mensaje_validacion(err),
                        'campo': '.'.join(str(x) for x in err.get('loc', ())[1:])})
    return JSONResponse({'detail': detalle}, status_code=422)


@app.exception_handler(Exception)
async def error_interno(request: Request, exc: Exception):
    """500 en JSON; el detalle completo queda solo en la consola del
    servidor (Uvicorn lo registra con el traceback)."""
    return JSONResponse({'detail': 'Error interno del servidor'}, status_code=500)


# ---------------------------------------------------- cabeceras, CORS y límite
CABECERAS_SEGURIDAD = {
    'X-Content-Type-Options': 'nosniff',
    'X-Frame-Options': 'DENY',
    'Referrer-Policy': 'same-origin',
    'Permissions-Policy': 'camera=(), microphone=(), geolocation=()',
    'Cross-Origin-Opener-Policy': 'same-origin',
    # Sin scripts ni estilos inline: el prototipo usa solo archivos propios.
    'Content-Security-Policy': ("default-src 'self'; script-src 'self'; "
                                "style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
                                "connect-src 'self'; object-src 'none'; base-uri 'self'; "
                                "form-action 'self'; frame-ancestors 'none'"),
}


@app.middleware('http')
async def cabeceras_y_limite(request: Request, call_next):
    """Límite general de peticiones por IP (ventana de un minuto), cabeceras
    de seguridad en toda respuesta y CORS solo para los orígenes declarados
    en KOTODUO_CORS_ORIGENES (nunca '*')."""
    ip = ip_cliente(request)
    if request.url.path != '/health' and not ventana_ok(VENTANA, ip, LIMITE_GENERAL):
        return JSONResponse({'detail': 'Demasiadas peticiones desde esta IP; '
                                       'espera un minuto y vuelve a intentarlo'},
                            status_code=429)
    origen = request.headers.get('origin')
    permitido = bool(origen) and origen in CORS_ORIGENES
    if request.method == 'OPTIONS' and permitido:
        r = Response(status_code=204)
        r.headers['Access-Control-Allow-Origin'] = origen
        r.headers['Access-Control-Allow-Methods'] = 'GET, POST, PATCH, OPTIONS'
        r.headers['Access-Control-Allow-Headers'] = 'Authorization, Content-Type, Accept'
        r.headers['Access-Control-Max-Age'] = '600'
        r.headers['Vary'] = 'Origin'
        return r
    respuesta = await call_next(request)
    for clave, valor in CABECERAS_SEGURIDAD.items():
        respuesta.headers.setdefault(clave, valor)
    if permitido:
        respuesta.headers['Access-Control-Allow-Origin'] = origen
        respuesta.headers['Vary'] = 'Origin'
    esquema = (request.headers.get('x-forwarded-proto') if CONFIA_PROXY
               else request.url.scheme)
    if esquema == 'https':
        # Solo detrás de TLS (Nginx con KOTODUO_CONFIA_PROXY=1).
        respuesta.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    return respuesta


# ------------------------------------------------- sin panel de administración
@app.get('/admin')
@app.get('/admin/{resto:path}')
def sin_panel_administracion():
    """Cero rastros de frameworks ajenos: no existe /admin/ ni HTML de
    gestión; la administración es por rol dentro de la propia aplicación."""
    raise HTTPException(404, 'Ruta no encontrada: esta aplicación no tiene panel de administración')


# ------------------------------------------------------------------ interfaz web (§8.2)
# Última línea de la API: todo lo que no sea un endpoint se resuelve con los
# archivos de prototipo/ desde este mismo proceso Uvicorn.
class InterfazSPA(StaticFiles):
    """Sirve la interfaz también en direcciones que no son un archivo.

    Una navegación del navegador (Accept: text/html) que no corresponde a un
    archivo recibe index.html; desde allí la propia interfaz normaliza la
    dirección a / cuando hay sesión abierta y a /Login cuando no la hay,
    de modo que escribir a mano una ruta equivocada nunca deja al usuario
    en una página de error. Las peticiones que no son navegación (scripts,
    pruebas, llamadas de la API) siguen recibiendo 404 en JSON, como exige
    el endurecimiento y registran las pruebas del Anexo K.
    """

    async def get_response(self, path, scope):
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code != 404:
                raise
            cabeceras = dict(scope.get('headers') or [])
            if b'text/html' in cabeceras.get(b'accept', b'').lower():
                return FileResponse(os.path.join(PROTOTIPO, 'index.html'))
            raise


app.mount('/', InterfazSPA(directory=PROTOTIPO, html=True), name='interfaz')
