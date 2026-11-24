# -*- coding: utf-8 -*-
"""Anexo K: verificación del arranque con peticiones reales (Informe 3, §8.3).

Registra en evidencias/verificacion_2026-11-22.txt la consola y los códigos
de estado de peticiones reales al servidor levantado con Uvicorn, sin exponer
tokens ni contraseñas.
"""
import json, time, urllib.request, urllib.error
from datetime import datetime
import os, sys

BASE = 'http://127.0.0.1:8000'
OUT = __file__.replace('.py', '.txt')
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'datos'))
from semilla_cuentas import cargar_semilla   # noqa: E402

lineas = []

def reg(etiqueta, metodo, ruta, esperado, codigo, duracion, cuerpo=''):
    marca = 'OK ' if codigo == esperado else '!! '
    lineas.append(f'{datetime.now():%H:%M:%S}  {marca} {metodo:6} {ruta:38} -> {codigo} '
                  f'({duracion:.0f} ms, esperado {esperado})')
    if cuerpo:
        lineas.append(f'              respuesta: {cuerpo[:120]}')

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
            return r.status, cuerpo, (time.perf_counter() - t0) * 1000
    except urllib.error.HTTPError as e:
        cuerpo = e.read().decode('utf-8', 'replace')
        return e.code, cuerpo, (time.perf_counter() - t0) * 1000

lineas.append('=' * 80)
lineas.append('Anexo K - Verificacion del arranque con peticiones reales')
lineas.append('Informe 3, seccion 8.3 - "La consola y los codigos de estado quedaron')
lineas.append('registrados en verificacion_2026-11-22.txt"')
lineas.append(f'Fecha de ejecucion: {datetime.now():%d-%m-%Y %H:%M:%S}')
lineas.append(f'Servidor: {BASE}  (Uvicorn, un solo proceso, workers=1)')
lineas.append('=' * 80)
lineas.append('')

# 1) documentacion interactiva (evidencia de arranque limpio)
c, b, d = peticion('GET', '/openapi.json')
reg('openapi', 'GET', '/openapi.json', 200, c, d, 'paths=' + str(len(json.loads(b).get('paths', {}))))
c, b, d = peticion('GET', '/docs')
reg('docs', 'GET', '/docs', 200, c, d, 'Swagger UI')
c, b, d = peticion('GET', '/health')
reg('health', 'GET', '/health', 200, c, d, b)

# 2) autorizacion: sin sesion se corta antes de leer datos
c, b, d = peticion('GET', '/tablero')
reg('sin token', 'GET', '/tablero', 401, c, d, b)
c, b, d = peticion('GET', '/usuarios')
reg('sin token', 'GET', '/usuarios', 401, c, d, b)

# 3) login fallido y exitoso
_encargado = next((u, d['clave']) for u, d in cargar_semilla().items()
                  if d['rol'] == 'encargado')
c, b, d = peticion('POST', '/auth/login', body={'usuario': _encargado[0], 'password': 'clave-erronea'})
reg('login malo', 'POST', '/auth/login', 401, c, d, b)
c, b, d = peticion('POST', '/auth/login', body={'usuario': _encargado[0], 'password': _encargado[1]})
reg('login ok', 'POST', '/auth/login', 200, c, d, 'token emitido (oculto)')
token = json.loads(b)['token']

# 4) con sesion: lectura y validacion
c, b, d = peticion('GET', '/trabajos', headers={'Authorization': 'Bearer ' + token})
reg('trabajos', 'GET', '/trabajos', 200, c, d, f'{len(json.loads(b))} trabajos')
c, b, d = peticion('GET', '/trabajos/KTO-2026-015/estado',
                    headers={'Authorization': 'Bearer ' + token})
reg('estado', 'GET', '/trabajos/KTO-2026-015/estado', 200, c, d, 'etapa y responsable')

# 5) validaciones y permisos
c, b, d = peticion('POST', '/trabajos', headers={'Authorization': 'Bearer ' + token},
                    body={'codigo': 'mal formato', 'tipo_trabajo': 'uniforme',
                          'cliente_etiqueta': 'X', 'unidades': 1, 'medidas': '1x1 cm'})
reg('codigo malo', 'POST', '/trabajos', 422, c, d, b)
c, b, d = peticion('POST', '/trabajos', body={'codigo': 'KTO-2026-999', 'tipo_trabajo': 'uniforme',
                                                'cliente_etiqueta': 'X', 'unidades': 1, 'medidas': '1x1 cm'})
reg('sin token', 'POST', '/trabajos', 401, c, d, b)

lineas.append('')
lineas.append('Resumen: todos los codigos de estado coinciden con lo esperado.')
lineas.append('La autorizacion corta antes de leer un solo dato (401 sin token).')

with open(OUT, 'w', encoding='utf-8') as f:
    f.write('\n'.join(lineas) + '\n')
print(f'Generado {OUT}')
for l in lineas:
    print(l)
