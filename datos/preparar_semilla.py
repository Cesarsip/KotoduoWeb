# -*- coding: utf-8 -*-
"""Crea api/credenciales_semilla.txt si no existe (clones nuevos y CI).

Las contraseñas se generan aleatorias en el propio equipo: nunca viajan en
el repositorio. Si el archivo ya existe no se toca, así las cuentas de la
demostración se mantienen estables mientras dure el proyecto.

    python datos/preparar_semilla.py
"""
import os
import secrets
import string

from semilla_cuentas import SEMILLA

# usuario, nombre completo, rol (los nombres son los de la semilla del proyecto)
CUENTAS = (
    ('aeo', 'Andrés Aedo', 'administrador'),
    ('bjaque', 'Benjamín Jaque', 'encargado'),
    ('msanchez', 'Marcos Sánchez', 'operario'),
    ('jrojas', 'Javier Rojas', 'vendedor'),
)


def clave_aleatoria() -> str:
    """Contraseña de prueba: 14 caracteres entre letras y números."""
    abecedario = string.ascii_letters + string.digits
    return 'Koto.' + ''.join(secrets.choice(abecedario) for _ in range(11))


def main():
    if os.path.exists(SEMILLA):
        print(f'Ya existe {SEMILLA} (no se modifica)')
        return 0
    lineas = ['Cuentas de prueba (semilla) - no usar en producción']
    for usuario, _nombre, rol in CUENTAS:
        lineas.append(f'{usuario} / {clave_aleatoria()} -> {rol}')
    os.makedirs(os.path.dirname(SEMILLA), exist_ok=True)
    with open(SEMILLA, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lineas) + '\n')
    print(f'Creado {SEMILLA} con {len(CUENTAS)} cuentas de prueba aleatorias')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
