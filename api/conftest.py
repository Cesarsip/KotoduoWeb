# -*- coding: utf-8 -*-
"""Reconstruye la base de datos antes de cada sesión de pruebas (aislamiento)."""
import io, os, subprocess, sys

BASE = os.path.dirname(os.path.abspath(__file__))
DATOS = os.path.join(BASE, '..', 'datos')


def pytest_sessionstart(session):
    subprocess.run([sys.executable, os.path.join(DATOS, 'ejecutar_datos.py')],
                   check=True, capture_output=True)
    rend = os.path.join(BASE, 'salida_rendimiento.txt')
    if os.path.exists(rend):
        os.remove(rend)
