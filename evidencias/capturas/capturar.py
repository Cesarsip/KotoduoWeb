# -*- coding: utf-8 -*-
"""Capturas Playwright de la aplicación Kotoduo (evidencia 2.1.3.5 / §5.3).

Requiere el servidor corriendo (la interfaz se sirve desde la misma API):

    cd api && uvicorn app:app --host 127.0.0.1 --port 8000

La URL puede cambiarse con la variable de entorno KOTODUO_URL para tomar las
mismas capturas desde la dirección pública una vez publicada la aplicación,
tal como prevé el Informe 3, §5.3.
"""
import os
from playwright.sync_api import sync_playwright

BASE = os.path.dirname(os.path.abspath(__file__))
URL = os.environ.get('KOTODUO_URL', 'http://127.0.0.1:8000/')


def nom(br, nombre):
    # dejar terminar la animación de aparición para no capturar texto lavado
    br.wait_for_timeout(450)
    ruta = os.path.join(BASE, nombre + '.png')
    br.screenshot(path=ruta, full_page=True)
    print('capturado', nombre, '->', URL)


def entrar(br, perfil, pantalla):
    br.click('button.link[data-user="%s"]' % perfil)
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
    entrar(br, 'msanchez|Koto.Op.2026!', '#p-operario')
    br.wait_for_selector('#btn-avance')
    nom(br, 'cap02_operario_tareas')

    # HU-02: registrar avance deja el aviso flotante (sin bloquear la pantalla)
    br.click('#btn-avance')
    br.wait_for_timeout(400)
    nom(br, 'cap03_operario_toast_avance')
    br.wait_for_timeout(3000)  # esperar a que desaparezca el aviso

    # HU-05: tablero con datos reales de la API
    salir(br)
    entrar(br, 'bjaque|Koto.Enca.2026', '#p-encargado')
    br.wait_for_selector('.tarjeta.mini')
    nom(br, 'cap04_encargado_tablero')

    # HU-03: formulario de nuevo trabajo con código sugerido
    br.click('#btn-nuevo')
    br.wait_for_selector('#p-nuevo.activa')
    br.wait_for_function("document.getElementById('t-codigo').value !== ''")
    nom(br, 'cap05_encargado_nuevo_trabajo')

    # HU-08: ficha de estado del pedido para el vendedor
    salir(br)
    entrar(br, 'jrojas|Koto.Vend.2026', '#p-vendedor')
    br.fill('#b-codigo', 'KTO-2026-015')
    br.click('#f-buscar button[type="submit"]')
    br.wait_for_selector('#resultado .tarjeta')
    nom(br, 'cap06_vendedor_estado_pedido')

    # HU-07: usuarios y bitácora del administrador
    salir(br)
    entrar(br, 'aeo|Koto.Admin.2026', '#p-admin')
    br.wait_for_selector('#tabla-usuarios tr')
    br.wait_for_selector('#tabla-bitacora tr')
    nom(br, 'cap07_admin_usuarios_bitacora')

    # Vistas móviles (diseño primero para planta)
    movil = navegador.new_page(viewport={'width': 375, 'height': 720})
    movil.goto(URL, wait_until='load')
    movil.wait_for_selector('#f-login')
    entrar(movil, 'msanchez|Koto.Op.2026!', '#p-operario')
    movil.wait_for_selector('#btn-avance')
    nom(movil, 'cap08_movil_operario')
    salir(movil)
    entrar(movil, 'bjaque|Koto.Enca.2026', '#p-encargado')
    movil.wait_for_selector('.tarjeta.mini')
    nom(movil, 'cap09_movil_tablero')

    navegador.close()
print('OK: 9 capturas')
