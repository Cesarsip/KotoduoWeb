# -*- coding: utf-8 -*-
"""Cuentas de prueba (semilla): única lectura del archivo de credenciales.

Las contraseñas NO viven en el repositorio: están en
api/credenciales_semilla.txt, que git ignora y que se entrega aparte con el
proyecto. El Informe 3, §7, lo dice así: "las cuentas de prueba se cargan
desde un archivo de semilla que vive fuera del código fuente".

Formato de cada línea del archivo:

    usuario / contraseña -> rol

La base de datos, las pruebas, las capturas y la verificación leen de aquí
para trabajar siempre con las mismas cuentas.
"""
import os
import re

BASE = os.path.dirname(os.path.abspath(__file__))
SEMILLA = (os.environ.get('KOTODUO_SEMILLA')
           or os.path.abspath(os.path.join(BASE, '..', 'api', 'credenciales_semilla.txt')))

FILA = re.compile(r'^\s*([a-z0-9._-]+)\s*/\s*(.+?)\s*->\s*([a-z_]+)\s*$')

ROLES_PRUEBA = ('administrador', 'encargado', 'operario', 'vendedor')


def cargar_semilla(ruta: str = None) -> dict:
    """Devuelve {'usuario': {'clave': ..., 'rol': ...}} desde el archivo."""
    ruta = ruta or SEMILLA
    if not os.path.exists(ruta):
        raise FileNotFoundError(
            'Falta el archivo de semilla de cuentas: ' + ruta + '\n'
            'Créalo con: python datos/preparar_semilla.py')
    cuentas: dict = {}
    with open(ruta, encoding='utf-8') as f:
        for linea in f:
            m = FILA.match(linea)
            if m:
                cuentas.setdefault(m.group(1), {'clave': m.group(2), 'rol': m.group(3)})
    faltan = [r for r in ROLES_PRUEBA
              if not any(c['rol'] == r for c in cuentas.values())]
    if faltan:
        raise ValueError('El archivo de semilla no tiene cuenta para: ' + ', '.join(faltan))
    return cuentas


def cuenta(rol: str) -> tuple:
    """(usuario, contraseña) de la cuenta de un rol de prueba."""
    for usuario, datos in cargar_semilla().items():
        if datos['rol'] == rol:
            return usuario, datos['clave']
    raise KeyError(f'La semilla no tiene cuenta para el rol {rol}')
