# -*- coding: utf-8 -*-
"""Reconstruye la base de datos antes de cada sesión de pruebas (aislamiento)."""
import io, os, subprocess, sys

BASE = os.path.dirname(os.path.abspath(__file__))
DATOS = os.path.join(BASE, '..', 'datos')


def pytest_sessionstart(session):
    # Reconstruye ambas bases. Si KOTODUO_DB / KOTODUO_DOC_DB apuntan a una
    # copia (como en el servidor), solo se reconstruye la copia: la base de
    # producción no se toca.
    for script in ('ejecutar_datos.py', 'crear_documentos.py'):
        subprocess.run([sys.executable, os.path.join(DATOS, script)],
                       check=True, capture_output=True)
    rend = os.path.join(BASE, 'salida_rendimiento.txt')
    if os.path.exists(rend):
        os.remove(rend)
