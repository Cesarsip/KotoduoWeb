# -*- coding: utf-8 -*-
"""Pruebas del plan de pruebas ES2: unitarias, integración, seguridad y rendimiento."""
import sys, os, time, random
from fastapi.testclient import TestClient

BASE_API = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_API)
sys.path.insert(0, os.path.join(BASE_API, '..', 'datos'))
from app import app, ROLES_PERMITIDOS  # noqa: E402
from semilla_cuentas import cargar_semilla  # noqa: E402

c = TestClient(app)

# Cuentas desde el archivo de semilla (fuera del repositorio): las mismas
# con las que se reconstruye la base en conftest.py.
_ALIAS_ROL = {'administrador': 'admin', 'encargado': 'encargado',
              'operario': 'operario', 'vendedor': 'vendedor'}
USUARIOS: dict = {}
for _usuario, _datos in cargar_semilla().items():
    if _datos['rol'] in _ALIAS_ROL:
        USUARIOS.setdefault(_ALIAS_ROL[_datos['rol']], (_usuario, _datos['clave']))
assert set(USUARIOS) == {'admin', 'encargado', 'operario', 'vendedor'}, \
    'la semilla no contiene las cuatro cuentas de prueba'


def token(rol: str) -> dict:
    u, p = USUARIOS[rol]
    r = c.post('/auth/login', json={'usuario': u, 'password': p})
    assert r.status_code == 200
    return {'Authorization': 'Bearer ' + r.json()['token']}


def codigo_nuevo() -> str:
    return f'KTO-2026-{random.randint(200, 999):03d}'


# ------------------------------ Unitarias (UT) ------------------------------
def test_UT01_matriz_rbac_cubre_los_cuatro_roles():
    assert ROLES_PERMITIDOS['crear_trabajo'] == {'encargado', 'administrador'}
    assert 'operario' not in ROLES_PERMITIDOS['ver_tablero']
    assert ROLES_PERMITIDOS['ver_bitacora'] == {'administrador'}


def test_UT02_login_rechaza_password_incorrecta():
    r = c.post('/auth/login', json={'usuario': 'bjaque', 'password': 'clave-equivocada'})
    assert r.status_code == 401


def test_UT03_codigo_de_trabajo_con_formato_invalido():
    h = token('encargado')
    r = c.post('/trabajos', headers=h, json={
        'codigo': 'mal formato', 'tipo_trabajo': 'uniforme',
        'cliente_etiqueta': 'Colegio Norte', 'unidades': 10,
        'medidas': '20x30 cm'})
    assert r.status_code == 422


def test_UT04_unidades_no_puede_ser_cero():
    h = token('encargado')
    r = c.post('/trabajos', headers=h, json={
        'codigo': codigo_nuevo(), 'tipo_trabajo': 'uniforme',
        'cliente_etiqueta': 'Club Norte', 'unidades': 0,
        'medidas': '20x30 cm'})
    assert r.status_code == 422


# --------------------------- Integración (IN) -------------------------------
def test_IN01_encargado_crea_trabajo_y_le_quedan_etapas():
    h = token('encargado')
    codigo = codigo_nuevo()
    r = c.post('/trabajos', headers=h, json={
        'codigo': codigo, 'tipo_trabajo': 'letrero',
        'cliente_etiqueta': 'Farmacia Central', 'pedido_ref': 'PED-INT-90',
        'unidades': 1, 'medidas': '80x30 cm', 'fecha_compromiso': '2026-01-01'})
    assert r.status_code == 201
    sig = c.get('/trabajos/siguiente', headers=h).json()
    assert sig.get('codigo') == codigo  # el trabajo nuevo encabeza la cola


def test_IN02_cerrar_etapa_registra_bitacora():
    h = token('encargado')
    # Trabajo con etapa abierta cuya etapa de diseño ya está aprobada
    # (semilla KTO-2026-014: diseño v1 aprobado, Confección en curso).
    trabajos = c.get('/trabajos', headers=h).json()
    objetivo = next(t for t in trabajos
                    if t['codigo'] == 'KTO-2026-014' and t['etapa_trabajo_id'])
    r = c.post(f"/etapas/{objetivo['etapa_trabajo_id']}/cerrar", headers=h)
    assert r.status_code == 200 and r.json()['estado'] == 'cerrada'
    b = c.get('/bitacora', headers=token('admin'),
              params={'entidad': 'etapas_trabajo',
                      'entidad_id': objetivo['etapa_trabajo_id']}).json()
    assert any(x['accion'] == 'cerrar_etapa' for x in b)


def test_IN03_tablero_refleja_estados():
    t = c.get('/tablero', headers=token('encargado')).json()
    assert sum(t.values()) >= 3


def test_IN04_alertas_de_insumos_bajo_umbral():
    a = c.get('/insumos/alertas', headers=token('vendedor')).json()
    assert any('Tinta' in x['nombre'] for x in a)


def test_IN05_etapa_diseno_no_se_cierra_sin_aprobacion():
    """IN-05 (HU-06): rechazo sin aprobación y cierre permitido después."""
    h = token('encargado')
    codigo = codigo_nuevo()
    r = c.post('/trabajos', headers=h, json={
        'codigo': codigo, 'tipo_trabajo': 'uniforme',
        'cliente_etiqueta': 'Escuela Nueva', 'unidades': 12,
        'medidas': '20x30 cm', 'fecha_compromiso': '2026-01-03'})
    assert r.status_code == 201
    trabajos = c.get('/trabajos', headers=h, params={'estado': 'en_diseño'}).json()
    etapa_diseno = next(t for t in trabajos if t['codigo'] == codigo)['etapa_trabajo_id']

    # 1) intentar cerrar sin versión aprobada -> rechazo
    assert c.post(f'/etapas/{etapa_diseno}/cerrar', headers=h).status_code == 409

    # 2) el encargado decide la versión pendiente del diseño
    d = c.post(f'/trabajos/{codigo}/disenos/1/decision', headers=h,
               json={'estado': 'aprobado', 'comentarios': 'Conforme con el cliente'})
    assert d.status_code == 200 and d.json()['estado'] == 'aprobado'

    # 3) después de aprobar -> cierre permitido y el trabajo pasa a producción
    assert c.post(f'/etapas/{etapa_diseno}/cerrar', headers=h).status_code == 200
    estados = {t['codigo']: t['estado_general']
               for t in c.get('/trabajos', headers=h).json()}
    assert estados[codigo] == 'en_producción'


def test_IN06_vendedor_consulta_estado_del_pedido():
    """IN-06 (HU-08): etapa y responsable, sin costos ni bitácora."""
    r = c.get('/trabajos/KTO-2026-015/estado', headers=token('vendedor'))
    assert r.status_code == 200
    d = r.json()
    assert d['etapa_actual'] and d['responsable'] != 'Sin asignar'
    assert d['etapas_cerradas'] < d['total_etapas']
    assert not any(k in d for k in ('costo', 'monto', 'precio', 'bitacora'))


# ----------------------------- Seguridad (SEG) -------------------------------
def test_SEG01_operario_no_puede_crear_trabajos():
    r = c.post('/trabajos', headers=token('operario'), json={
        'codigo': codigo_nuevo(), 'tipo_trabajo': 'uniforme',
        'cliente_etiqueta': 'Club Norte', 'unidades': 2, 'medidas': '20x30'})
    assert r.status_code == 403


def test_SEG02_vendedor_no_puede_ver_bitacora():
    r = c.get('/bitacora', headers=token('vendedor'),
              params={'entidad': 'trabajos', 'entidad_id': 1})
    assert r.status_code == 403


def test_SEG03_peticion_sin_token_es_rechazada():
    assert c.get('/tablero').status_code in (401, 403)


def test_SEG04_token_falso_es_rechazado():
    r = c.get('/tablero', headers={'Authorization': 'Bearer token-falso'})
    assert r.status_code == 401


def test_SEG05_inyeccion_sql_no_alcanza_a_ejecutarse():
    h = token('encargado')
    payloads = ["'; DROP TABLE trabajos; --", "1 OR 1=1", "KTO' OR '1'='1"]
    for i, payload in enumerate(payloads):
        r = c.post('/trabajos', headers=h, json={
            'codigo': f'KTO-2026-{700 + i}', 'tipo_trabajo': 'uniforme',
            'cliente_etiqueta': payload, 'unidades': 1, 'medidas': '20x30 cm'})
        # la consulta parametrizada neutraliza el payload: se guarda como texto
        # literal (201) o se rechaza por unicidad en reintentos (409)
        assert r.status_code in (201, 409)
    ok = c.get('/tablero', headers=token('encargado'))
    assert ok.status_code == 200  # la tabla trabajos sigue viva


def test_SEG06_campos_de_texto_rechazan_etiquetas_html():
    h = token('encargado')
    r = c.post('/trabajos', headers=h, json={
        'codigo': codigo_nuevo(), 'tipo_trabajo': 'uniforme',
        'cliente_etiqueta': '<script>alert(1)</script>', 'unidades': 1,
        'medidas': '20x30 cm'})
    assert r.status_code == 422


# ----------------------------- Rendimiento (RND) -----------------------------
def test_RND01_tablero_responde_rapido_bajo_repeticion():
    h = token('encargado')
    c.get('/tablero', headers=h)  # calentamiento
    n, inicio = 200, time.perf_counter()
    for _ in range(n):
        assert c.get('/tablero', headers=h).status_code == 200
    total = time.perf_counter() - inicio
    promedio = total / n
    with open(os.path.join(os.path.dirname(__file__), 'salida_rendimiento.txt'),
              'a', encoding='utf-8') as f:
        f.write(f'GET /tablero x{n}: total {total:.3f}s, promedio {promedio*1000:.1f} ms/req\n')
    assert promedio < 0.1  # umbral local de diseño: < 100 ms promedio
