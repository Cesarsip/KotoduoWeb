# -*- coding: utf-8 -*-
"""Capturas Playwright de la aplicación Kotoduo (evidencia 2.1.3.5 / §5.3).

Requiere el servidor corriendo (la interfaz se sirve desde la misma API):

    cd api && uvicorn app:app --host 127.0.0.1 --port 8000

La URL puede cambiarse con la variable de entorno KOTODUO_URL para tomar las
mismas capturas desde la dirección pública una vez publicada la aplicación,
tal como prevé el Informe 3, §5.3.
"""
import os
import sys
from playwright.sync_api import sync_playwright

BASE = os.path.dirname(os.path.abspath(__file__))
URL = os.environ.get('KOTODUO_URL', 'http://127.0.0.1:8000/')

# Cuentas desde el archivo de semilla (fuera del repositorio): nunca están
# en este script ni en la interfaz.
sys.path.insert(0, os.path.join(BASE, '..', '..', 'datos'))
from semilla_cuentas import cargar_semilla   # noqa: E402

CUENTAS = {d['rol']: (u, d['clave']) for u, d in cargar_semilla().items()}


def nom(br, nombre):
    # dejar terminar la animación de aparición para no capturar texto lavado
    br.wait_for_timeout(450)
    # Captura con el viewport redimensionado a la altura de la página en lugar
    # de full_page: con captureBeyondViewport, Chromium pinta la barra inferior
    # (position: fixed) dos veces y deja una banda fantasma a mitad de la imagen.
    tam = br.viewport_size
    alto = br.evaluate('() => document.documentElement.scrollHeight')
    br.set_viewport_size({'width': tam['width'], 'height': alto})
    br.wait_for_timeout(150)
    ruta = os.path.join(BASE, nombre + '.png')
    br.screenshot(path=ruta)
    br.set_viewport_size(tam)
    br.wait_for_timeout(80)
    print('capturado', nombre, '->', URL)


def entrar(br, rol, pantalla):
    """Inicio de sesión como en la interfaz real: el botón del perfil rellena
    el usuario y la contraseña se teclea (no vive en el código)."""
    usuario, clave = CUENTAS[rol]
    br.click('button.link[data-user="%s"]' % usuario)
    br.fill('#i-clave', clave)
    br.click('#f-login button[type="submit"]')
    br.wait_for_selector(pantalla + '.activa')


def salir(br):
    br.click('#btn-salir')
    br.wait_for_selector('#p-login.activa')
    # el aviso "Sesión cerrada" no debe colarse en la siguiente captura
    br.wait_for_selector('#toast', state='hidden', timeout=6000)


with sync_playwright() as p:
    navegador = p.chromium.launch()
    br = navegador.new_page(viewport={'width': 1280, 'height': 900})
    br.goto(URL, wait_until='load')
    br.wait_for_selector('#f-login')
    nom(br, 'cap01_login')

    # HU-07 / HU-01: operario con su cola de trabajo real
    entrar(br, 'operario', '#p-operario')
    br.wait_for_selector('#btn-avance')
    nom(br, 'cap02_operario_tareas')

    # HU-02: registrar avance deja el aviso flotante (sin bloquear la pantalla)
    br.click('#btn-avance')
    br.wait_for_timeout(400)
    nom(br, 'cap03_operario_toast_avance')
    br.wait_for_timeout(3000)  # esperar a que desaparezca el aviso

    # HU-05: tablero con datos reales de la API
    salir(br)
    entrar(br, 'encargado', '#p-encargado')
    br.wait_for_selector('.tarjeta.mini')
    nom(br, 'cap04_encargado_tablero')

    # HU-03: formulario de nuevo trabajo con código sugerido
    br.click('#btn-nuevo')
    br.wait_for_selector('#p-nuevo.activa')
    # esperar el código sugerido sin wait_for_function: la CSP de la API
    # (script-src 'self') bloquea el eval que Playwright usa en esa función
    for _ in range(40):
        if br.input_value('#t-codigo').strip():
            break
        br.wait_for_timeout(150)
    nom(br, 'cap05_encargado_nuevo_trabajo')

    # HU-08: ficha de estado del pedido para el vendedor
    salir(br)
    entrar(br, 'vendedor', '#p-vendedor')
    br.fill('#b-codigo', 'KTO-2026-015')
    br.click('#f-buscar button[type="submit"]')
    br.wait_for_selector('#resultado .tarjeta')
    nom(br, 'cap06_vendedor_estado_pedido')

    # HU-07: usuarios y bitácora del administrador
    salir(br)
    entrar(br, 'administrador', '#p-admin')
    br.wait_for_selector('#tabla-usuarios tr')
    br.wait_for_selector('#tabla-bitacora tr')
    nom(br, 'cap07_admin_usuarios_bitacora')

    # Vistas móviles (diseño primero para planta)
    movil = navegador.new_page(viewport={'width': 375, 'height': 720})
    movil.goto(URL, wait_until='load')
    movil.wait_for_selector('#f-login')
    entrar(movil, 'operario', '#p-operario')
    movil.wait_for_selector('#btn-avance')
    nom(movil, 'cap08_movil_operario')
    salir(movil)
    entrar(movil, 'encargado', '#p-encargado')
    movil.wait_for_selector('.tarjeta.mini')
    nom(movil, 'cap09_movil_tablero')

    navegador.close()
print('OK: 9 capturas')
