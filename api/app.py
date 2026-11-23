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

Todo el acceso a datos usa consultas parametrizadas (OWASP A03).
No hay secretos ni variables de entorno en el código: las credenciales de
prueba viven solo en el archivo de semilla, fuera del repositorio.
"""
import os, sqlite3, secrets, datetime
from typing import Optional, Literal
from fastapi import FastAPI, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator, model_validator
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from tinydb import TinyDB, Query

BASE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE, '..', 'datos', 'kotoduo.db')
DOC_PATH = os.path.join(BASE, '..', 'datos', 'documentos.json')
PROTOTIPO = os.path.join(BASE, '..', 'prototipo')

ph = PasswordHasher()
app = FastAPI(title='Kotoduo API')
bearer = HTTPBearer()

# Sesiones en memoria: decisión de i +1 trabajador registrada en el informe.
SESIONES: dict[str, int] = {}

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
    uid = SESIONES.get(cred.credentials)
    if uid is None:
        raise HTTPException(401, 'Sesión inválida o expirada')
    row = db.execute('SELECT id, usuario, nombre, rol, activo FROM usuarios WHERE id=?',
                     (uid,)).fetchone()
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


class DisenoIn(BaseModel):
    """Nueva versión de diseño enviada a aprobación (HU-06)."""
    archivo: str = Field(min_length=3, max_length=120)
    formato: Literal['svg', 'png', 'pdf', 'jpg'] = 'svg'
    paleta: list[str] = Field(default_factory=list, max_length=10)
    variantes: list[VarianteIn] = Field(default_factory=list, max_length=10)
    observaciones: list[str] = Field(default_factory=list, max_length=10)

    @field_validator('archivo', 'observaciones')
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
    password: str = Field(min_length=8, max_length=72)
    rol: Literal['operario', 'encargado', 'vendedor', 'administrador']

    @field_validator('nombre')
    @classmethod
    def sin_html(cls, v: str):
        if '<' in v or '>' in v:
            raise ValueError('no se aceptan etiquetas HTML en los campos de texto')
        return v


class UsuarioPatch(BaseModel):
    activo: Optional[bool] = None
    rol: Optional[Literal['operario', 'encargado', 'vendedor', 'administrador']] = None

    @model_validator(mode='after')
    def al_menos_un_campo(self):
        if self.activo is None and self.rol is None:
            raise ValueError('indica al menos un campo: activo o rol')
        return self


# ------------------------------------------------------------------ autenticación
@app.post('/auth/login')
def login(body: Login, db=Depends(get_db)):
    row = db.execute('SELECT id, usuario, nombre, rol, password_hash, activo '
                     'FROM usuarios WHERE usuario=?', (body.usuario,)).fetchone()
    if not row or not row['activo']:
        raise HTTPException(401, 'Credenciales inválidas')
    try:
        ph.verify(row['password_hash'], body.password)
    except VerifyMismatchError:
        raise HTTPException(401, 'Credenciales inválidas')
    if ph.check_needs_rehash(row['password_hash']):
        db.execute('UPDATE usuarios SET password_hash=? WHERE id=?',
                   (ph.hash(body.password), row['id']))
        db.commit()
    token = secrets.token_urlsafe(24)
    SESIONES[token] = row['id']
    return {'token': token, 'usuario': row['usuario'],
            'nombre': row['nombre'], 'rol': row['rol']}


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
def cerrar_etapa(etapa_id: int, db=Depends(get_db), user=Depends(requiere('cerrar_etapa'))):
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
    db.commit()
    return {'etapa': etapa_id, 'trabajo': fila['codigo'], 'estado': 'cerrada',
            'estado_trabajo': nuevo or fila['estado_general']}


# ------------------------------------------------------------------ HU-03
@app.post('/trabajos', status_code=201)
def crear_trabajo(body: TrabajoIn, db=Depends(get_db), user=Depends(requiere('crear_trabajo'))):
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
    bitacora(db, user, 'crear', 'trabajos', cur.lastrowid, None, body.codigo)
    db.commit()
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
def estado_pedido(codigo: str, db=Depends(get_db),
                  user=Depends(requiere('ver_estado_pedido'))):
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
def listar_disenos(codigo: str, db=Depends(get_db),
                   user=Depends(requiere('ver_disenos'))):
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
def nueva_version_diseno(codigo: str, body: DisenoIn, db=Depends(get_db),
                         user=Depends(requiere('registrar_diseno'))):
    """Registra una nueva versión de diseño y la deja pendiente de decisión."""
    t = trabajo_o_404(db, codigo)
    ultima = db.execute('SELECT MAX(version) AS v FROM aprobaciones_diseno '
                        'WHERE trabajo_id=?', (t['id'],)).fetchone()['v'] or 0
    version = ultima + 1
    try:
        db.execute('''INSERT INTO aprobaciones_diseno (trabajo_id, version, estado)
                      VALUES (?,?, 'pendiente')''', (t['id'], version))
    except sqlite3.IntegrityError:
        raise HTTPException(409, 'La versión de diseño ya existe')
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
    bitacora(db, user, 'crear_version_diseno', 'aprobaciones_diseno',
             t['id'] * 100 + version, None, f'{codigo} v{version} pendiente')
    db.commit()
    return {'codigo': codigo, 'version': version, 'estado': 'pendiente'}


@app.post('/trabajos/{codigo}/disenos/{version}/decision')
def decidir_diseno(codigo: str, version: int, body: DecisionIn, db=Depends(get_db),
                   user=Depends(requiere('decidir_diseno'))):
    """Aprueba o rechaza una versión de diseño (HU-06 / IN-05)."""
    t = trabajo_o_404(db, codigo)
    fila = db.execute('SELECT * FROM aprobaciones_diseno WHERE trabajo_id=? AND version=?',
                      (t['id'], version)).fetchone()
    if not fila:
        raise HTTPException(404, 'Versión de diseño inexistente')
    if fila['estado'] != 'pendiente':
        raise HTTPException(409, 'La versión de diseño ya fue decidida')

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

    # Se mantiene sincronizada la ficha documental (TinyDB).
    q = Query()
    DISENOS.update({'aprobado': body.estado == 'aprobado',
                    'decidido_por': user['usuario'],
                    'fecha': datetime.datetime.now().strftime('%Y-%m-%d %H:%M')},
                   (q.trabajo_codigo == codigo) & (q.version == version))
    db.commit()
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
def bitacora_lista(entidad: Optional[str] = None, entidad_id: Optional[int] = None,
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
    try:
        cur = db.execute('INSERT INTO usuarios (usuario, nombre, password_hash, rol) '
                         'VALUES (?,?,?,?)',
                         (body.usuario, body.nombre, ph.hash(body.password), body.rol))
    except sqlite3.IntegrityError:
        raise HTTPException(409, 'Usuario duplicado o rol no válido')
    bitacora(db, user, 'alta_usuario', 'usuarios', cur.lastrowid, None, body.usuario)
    db.commit()
    return {'id': cur.lastrowid, 'usuario': body.usuario, 'nombre': body.nombre,
            'rol': body.rol, 'activo': 1}


@app.patch('/usuarios/{usuario_id}')
def modificar_usuario(usuario_id: int, body: UsuarioPatch, db=Depends(get_db),
                      user=Depends(requiere('administrar_usuarios'))):
    fila = db.execute('SELECT * FROM usuarios WHERE id=?', (usuario_id,)).fetchone()
    if not fila:
        raise HTTPException(404, 'Usuario inexistente')
    if fila['id'] == user['id'] and body.activo is False:
        raise HTTPException(409, 'No puedes desactivar tu propia cuenta')
    if fila['id'] == user['id'] and body.rol and body.rol != fila['rol']:
        raise HTTPException(409, 'No puedes cambiar tu propio rol')

    if body.activo is not None and body.activo != bool(fila['activo']):
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
    db.commit()
    actualizado = db.execute('SELECT id, usuario, nombre, rol, activo FROM usuarios '
                             'WHERE id=?', (usuario_id,)).fetchone()
    return dict(actualizado)


# ------------------------------------------------------------------ interfaz web (§8.2)
# Última línea de la API: todo lo que no sea un endpoint se resuelve con los
# archivos de prototipo/ desde este mismo proceso Uvicorn.
app.mount('/', StaticFiles(directory=PROTOTIPO, html=True), name='interfaz')
