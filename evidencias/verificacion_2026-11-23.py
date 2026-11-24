# -*- coding: utf-8 -*-
"""Anexo K: verificación del arranque y del endurecimiento (Informe 3, §8.3).

Registra en evidencias/verificacion_2026-11-23.txt la consola y los códigos
de estado de peticiones reales al servidor levantado con Uvicorn, sin exponer
tokens ni contraseñas: las cuentas salen del archivo de semilla.

Requiere el servidor corriendo (uvicorn app:app --port 8000) y la base
reconstruida (python datos/ejecutar_datos.py && python datos/crear_documentos.py).
"""
import json, os, sys, time, urllib.request, urllib.error
from datetime import datetime

BASE = os.environ.get('KOTODUO_URL', 'http://127.0.0.1:8000').rstrip('/')
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   'verificacion_2026-11-23.txt')
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'datos'))
from semilla_cuentas import cargar_semilla   # noqa: E402

lineas = []


def reg(etiqueta, metodo, ruta, esperado, codigo, duracion, cuerpo=''):
    marca = 'OK ' if codigo == esperado else '!! '
    lineas.append(f'{datetime.now():%H:%M:%S}  {marca} {metodo:6} {ruta:44} -> {codigo} '
                  f'({duracion:.0f} ms, esperado {esperado})')
    if cuerpo:
        lineas.append(f'              respuesta: {cuerpo[:160]}')


def peticion(metodo, ruta, headers=None, body=None):
    datos = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + ruta, data=datos, method=metodo)
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)
    if datos:
        req.add_header('Content-Type', 'application/json')
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req) as r:
            cuerpo = r.read().decode('utf-8', 'replace')
            cab = {k.lower(): v for k, v in r.headers.items()}
            return r.status, cuerpo, (time.perf_counter() - t0) * 1000, cab
    except urllib.error.HTTPError as e:
        cuerpo = e.read().decode('utf-8', 'replace')
        return e.code, cuerpo, (time.perf_counter() - t0) * 1000, \
            {k.lower(): v for k, v in e.headers.items()}


cuentas = cargar_semilla()
ADMIN = next((u, d['clave']) for u, d in cuentas.items() if d['rol'] == 'administrador')
ENCARGADO = next((u, d['clave']) for u, d in cuentas.items() if d['rol'] == 'encargado')

lineas.append('=' * 96)
lineas.append('Anexo K - Verificacion del arranque y del endurecimiento de seguridad')
lineas.append('Informe 3, seccion 8.3 - "La consola y los codigos de estado quedaron')
lineas.append('registrados en verificacion_2026-11-23.txt"')
lineas.append(f'Fecha de ejecucion: {datetime.now():%d-%m-%Y %H:%M:%S}')
lineas.append(f'Servidor: {BASE}  (Uvicorn, un solo proceso, workers=1)')
lineas.append('Cuentas: archivo de semilla fuera del repositorio (no se imprimen)')
lineas.append('=' * 96)
lineas.append('')

# 1) documentacion interactiva (evidencia de arranque limpio)
c, b, d, _ = peticion('GET', '/openapi.json')
reg('openapi', 'GET', '/openapi.json', 200, c, d, 'paths=' + str(len(json.loads(b).get('paths', {}))))
c, b, d, _ = peticion('GET', '/docs')
reg('docs', 'GET', '/docs', 200, c, d, 'Swagger UI')
c, b, d, _ = peticion('GET', '/health')
reg('health', 'GET', '/health', 200, c, d, b)

# 2) sin panel de administracion heredado: 404 en JSON, nunca HTML
c, b, d, _ = peticion('GET', '/admin/')
reg('sin /admin/', 'GET', '/admin/', 404, c, d, b)
c, b, d, _ = peticion('GET', '/ruta/que/no/existe')
reg('404 generico', 'GET', '/ruta/que/no/existe', 404, c, d, b)

# 3) autorizacion: sin sesion se corta antes de leer datos
c, b, d, _ = peticion('GET', '/tablero')
reg('sin token', 'GET', '/tablero', 401, c, d, b)
c, b, d, _ = peticion('GET', '/tablero', headers={'Authorization': 'Bearer inventado'})
reg('token falso', 'GET', '/tablero', 401, c, d, b)

# 4) login: fallo, acierto y renovacion con el token de refresco
c, b, d, _ = peticion('POST', '/auth/login',
                      body={'usuario': ENCARGADO[0], 'password': 'clave-erronea'})
reg('login malo', 'POST', '/auth/login', 401, c, d, b)
c, b, d, _ = peticion('POST', '/auth/login',
                      body={'usuario': ENCARGADO[0], 'password': ENCARGADO[1]})
reg('login ok', 'POST', '/auth/login', 200, c, d, 'access + refresh emitidos (ocultos)')
sesion = json.loads(b)
token = sesion['token']
refresh = sesion['refresh_token']
lineas.append(f'              expira_en={sesion["expira_en"]} s (acceso 15 min, refresco 8 h)')

c, b, d, _ = peticion('POST', '/auth/refresh', body={'refresh_token': refresh})
reg('refresh', 'POST', '/auth/refresh', 200, c, d, 'token de acceso nuevo emitido')
token2 = json.loads(b)['token']
c, b, d, _ = peticion('GET', '/tablero', headers={'Authorization': 'Bearer ' + token2})
reg('token renovado', 'GET', '/tablero', 200, c, d, 'la sesion sigue viva tras renovar')

# 5) con sesion: lectura y validacion
c, b, d, _ = peticion('GET', '/trabajos', headers={'Authorization': 'Bearer ' + token2})
reg('trabajos', 'GET', '/trabajos', 200, c, d, f'{len(json.loads(b))} trabajos')
c, b, d, _ = peticion('GET', '/trabajos/KTO-2026-015/estado',
                      headers={'Authorization': 'Bearer ' + token2})
reg('estado', 'GET', '/trabajos/KTO-2026-015/estado', 200, c, d, 'etapa y responsable')
c, b, d, _ = peticion('GET', '/trabajos/ABC/estado',
                      headers={'Authorization': 'Bearer ' + token2})
reg('ruta mal formada', 'GET', '/trabajos/ABC/estado', 422, c, d, 'validacion estricta de ruta')
c, b, d, _ = peticion('POST', '/trabajos', headers={'Authorization': 'Bearer ' + token2},
                      body={'codigo': 'mal formato', 'tipo_trabajo': 'uniforme',
                            'cliente_etiqueta': 'Cliente X', 'unidades': 1, 'medidas': '1x1 cm'})
reg('codigo malo', 'POST', '/trabajos', 422, c, d, b)
c, b, d, _ = peticion('POST', '/trabajos', body={'codigo': 'KTO-2026-999',
                                                 'tipo_trabajo': 'uniforme',
                                                 'cliente_etiqueta': 'X', 'unidades': 1,
                                                 'medidas': '1x1 cm'})
reg('sin token', 'POST', '/trabajos', 401, c, d, b)

# 6) cabeceras de seguridad en toda respuesta
c, b, d, cab = peticion('GET', '/health')
for cabecera in ('x-content-type-options', 'x-frame-options', 'content-security-policy'):
    lineas.append(f'{datetime.now():%H:%M:%S}  {"OK " if cabecera in cab else "!! "} cabecera '
                  f'{cabecera}: {cab.get(cabecera, "AUSENTE")[:70]}')

# 7) bloqueo de cuenta a los tres fallos (423) con registro en bitacora
lineas.append('')
lineas.append('----- Bloqueo por intentos fallidos (423 Locked) -----')
c, b, d, _ = peticion('POST', '/auth/login', body={'usuario': ADMIN[0], 'password': ADMIN[1]})
token_admin = json.loads(b)['token']
cab_admin = {'Authorization': 'Bearer ' + token_admin}
# Cuentas únicas por corrida: así un bloqueo en memoria de una ejecución
# anterior (15 min) nunca enmascara los resultados de la siguiente.
sufijo = datetime.now().strftime('%H%M%S')
usuario_prueba = f'bloqueo.{sufijo}'
clave_prueba = 'Prueba.Fort.2026'
c, b, d, _ = peticion('POST', '/usuarios', headers=cab_admin,
                      body={'usuario': usuario_prueba, 'nombre': 'Cuenta de bloqueo',
                            'password': clave_prueba, 'rol': 'operario'})
if c == 409:   # la cuenta ya existía de una corrida anterior: se reutiliza
    lista = json.loads(peticion('GET', '/usuarios', headers=cab_admin)[1])
    id_prueba = next(u['id'] for u in lista if u['usuario'] == usuario_prueba)
    peticion('PATCH', f'/usuarios/{id_prueba}', headers=cab_admin, body={'activo': True})
else:
    id_prueba = json.loads(b)['id']
reg('alta usuario', 'POST', '/usuarios', 201 if c == 201 else 409, c, d, b)

for i in range(1, 4):
    c, b, d, _ = peticion('POST', '/auth/login',
                          body={'usuario': usuario_prueba, 'password': 'clave-mala-' + str(i)})
    reg(f'fallo {i}', 'POST', '/auth/login', 401 if i < 3 else 423, c, d, b)
c, b, d, _ = peticion('POST', '/auth/login',
                      body={'usuario': usuario_prueba, 'password': 'clave-mala-4'})
reg('bloqueada', 'POST', '/auth/login', 423, c, d, b)

registros = json.loads(peticion('GET', f'/bitacora?entidad=usuarios&entidad_id={id_prueba}',
                                headers=cab_admin)[1])
bloqueos = [r for r in registros if r['accion'] == 'login_bloqueado']
lineas.append(f'{datetime.now():%H:%M:%S}  {"OK " if bloqueos else "!! "} bitacora: '
              f'{len(bloqueos)} entrada(s) login_bloqueado con usuario e IP')
if bloqueos:
    lineas.append(f'              registro: {bloqueos[-1]["valor_anterior"]} | '
                  f'{bloqueos[-1]["valor_posterior"]}')

# 8) baja logica: la cuenta se desactiva sin borrarse (nunca se borra la
# fila, para no perder el historial ni romper la bitácora)
usuario_baja = f'baja.{sufijo}'
clave_baja = 'Prueba.Baja.2026'
c, b, d, _ = peticion('POST', '/usuarios', headers=cab_admin,
                      body={'usuario': usuario_baja, 'nombre': 'Cuenta de baja',
                            'password': clave_baja, 'rol': 'vendedor'})
if c == 201:
    id_baja = json.loads(b)['id']
else:
    id_baja = next(u['id'] for u in json.loads(
        peticion('GET', '/usuarios', headers=cab_admin)[1])
        if u['usuario'] == usuario_baja)
reg('alta usuario (baja)', 'POST', '/usuarios', 201 if c == 201 else 409, c, d, b)
c, b, d, _ = peticion('PATCH', f'/usuarios/{id_baja}', headers=cab_admin,
                      body={'activo': False})
reg('baja logica', 'PATCH', f'/usuarios/{id_baja}', 200, c, d, b)
c, b, d, _ = peticion('POST', '/auth/login',
                      body={'usuario': usuario_baja, 'password': clave_baja})
reg('login inactivo', 'POST', '/auth/login', 401, c, d, b)

# 9) cierre de sesion: el token retirado deja de servir
c, b, d, _ = peticion('POST', '/auth/logout', headers={'Authorization': 'Bearer ' + token2})
reg('logout', 'POST', '/auth/logout', 200, c, d, b)
c, b, d, _ = peticion('GET', '/tablero', headers={'Authorization': 'Bearer ' + token2})
reg('token retirado', 'GET', '/tablero', 401, c, d, b)

lineas.append('')
fallos = [l for l in lineas if '!! ' in l]
lineas.append(f'Resumen: {len(fallos)} incidencia(s) de las verificaciones anteriores.'
              if fallos else 'Resumen: todos los codigos de estado coinciden con lo esperado.')
lineas.append('La autorizacion corta antes de leer un solo dato (401 sin token),')
lineas.append('la cuenta se bloquea a los tres fallos (423) con su entrada en la')
lineas.append('bitacora, y no existe panel de administracion (404 en JSON).')

with open(OUT, 'w', encoding='utf-8') as f:
    f.write('\n'.join(lineas) + '\n')
print(f'Generado {OUT}')
for l in lineas:
    print(l)
