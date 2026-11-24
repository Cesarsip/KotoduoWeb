# -*- coding: utf-8 -*-
"""Prueba en navegador del redirect de rutas desconocidas.

Escenarios:
  1. Sin sesión: abrir /HOLA  -> la URL pasa a /Login (y / sigue en /Login).
  2. Con sesión: abrir /HOLA  -> la URL pasa a / (y /Login pasa a /).
  3. Cerrar sesión desde /    -> la URL pasa a /Login.
No guarda capturas: es verificación, no evidencia.
"""
import os
import sys
from playwright.sync_api import sync_playwright

BASE = os.path.dirname(os.path.abspath(__file__))
URL = os.environ.get('KOTODUO_URL', 'http://127.0.0.1:8000').rstrip('/')
sys.path.insert(0, os.path.join(BASE, '..', 'datos'))
from semilla_cuentas import cargar_semilla   # noqa: E402

CUENTAS = {d['rol']: (u, d['clave']) for u, d in cargar_semilla().items()}
fallos = []


def ok(etiqueta, condicion, detalle=''):
    print(('OK   ' if condicion else 'FALLO') + ' ' + etiqueta +
          ('  [%s]' % detalle if detalle else ''))
    if not condicion:
        fallos.append(etiqueta)


with sync_playwright() as p:
    br = p.chromium.launch()
    pag = br.new_page(viewport={'width': 1280, 'height': 900})

    # --- 1) sin sesión ---------------------------------------------------
    pag.goto(URL + '/HOLA', wait_until='load')
    pag.wait_for_selector('#f-login')
    ok('sin sesión: /HOLA muestra el login', True)
    ok('sin sesión: la URL queda en /Login', pag.url == URL + '/Login', pag.url)

    pag.goto(URL + '/', wait_until='load')
    pag.wait_for_selector('#f-login')
    ok('sin sesión: / se normaliza a /Login', pag.url == URL + '/Login', pag.url)

    pag.goto(URL + '/cualquier/cosa', wait_until='load')
    pag.wait_for_selector('#f-login')
    ok('sin sesión: ruta profunda se normaliza a /Login',
       pag.url == URL + '/Login', pag.url)

    # --- 2) con sesión ---------------------------------------------------
    usuario, clave = CUENTAS['encargado']
    pag.click('button.link[data-user="%s"]' % usuario)
    pag.fill('#i-clave', clave)
    pag.click('#f-login button[type="submit"]')
    pag.wait_for_selector('#p-encargado.activa')
    ok('con sesión: al entrar la URL queda en /', pag.url == URL + '/', pag.url)

    pag.goto(URL + '/HOLA', wait_until='load')
    pag.wait_for_selector('#p-encargado.activa, #p-operario.activa, #p-admin.activa, #p-vendedor.activa')
    ok('con sesión: /HOLA se normaliza a /', pag.url == URL + '/', pag.url)

    pag.goto(URL + '/Login', wait_until='load')
    pag.wait_for_selector('#p-encargado.activa, #p-operario.activa, #p-admin.activa, #p-vendedor.activa')
    ok('con sesión: /Login se normaliza a /', pag.url == URL + '/', pag.url)

    # --- 3) al cerrar sesión --------------------------------------------
    pag.click('#btn-salir')
    pag.wait_for_selector('#p-login.activa')
    ok('al cerrer sesión la URL pasa a /Login', pag.url == URL + '/Login', pag.url)

    br.close()

print()
if fallos:
    print('%d FALLO(S): %s' % (len(fallos), ', '.join(fallos)))
    sys.exit(1)
print('Todo OK')
