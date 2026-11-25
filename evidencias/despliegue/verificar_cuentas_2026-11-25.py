# -*- coding: utf-8 -*-
"""Comprueba el inicio de sesion de las cuatro cuentas de la semilla contra
la URL publica. No imprime contrasenas ni tokens.

Uso (en la instancia, desde /home/ubuntu/KotoduoWeb):

    .venv/bin/python evidencias/despliegue/verificar_cuentas_2026-11-25.py \
        > evidencias/despliegue/verificacion_cuentas_2026-11-25.txt
"""
import datetime
import json
import sys
import urllib.error
import urllib.request

sys.path.insert(0, '/home/ubuntu/KotoduoWeb/datos')
from semilla_cuentas import cargar_semilla  # noqa: E402

BASE = 'https://kotoduo.duckdns.org'
ESPERADOS = {'administrador', 'encargado', 'operario', 'vendedor'}


def main() -> int:
    print('-' * 60)
    print('VERIFICACION DE LAS CUENTAS DE LA SEMILLA - KOTODUO PRODUCCION')
    print('-' * 60)
    print('Fecha (UTC) .........', datetime.datetime.now(datetime.timezone.utc)
          .strftime('%Y-%m-%d %H:%M:%S'))
    print('URL publica .........', BASE)
    print()
    cuentas = cargar_semilla()
    vistos = set()
    fallos = 0
    for usuario, datos in sorted(cuentas.items(), key=lambda x: x[1]['rol']):
        cuerpo = json.dumps({'usuario': usuario,
                             'password': datos['clave']}).encode('utf-8')
        peticion = urllib.request.Request(
            BASE + '/auth/login', data=cuerpo, method='POST',
            headers={'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(peticion, timeout=15) as respuesta:
                carga = json.load(respuesta)
                rol = carga.get('rol')
                tiene_token = bool(carga.get('token'))
                tiene_refresco = bool(carga.get('refresh_token'))
                estado = 'OK' if (respuesta.status == 200 and rol == datos['rol']
                                  and tiene_token and tiene_refresco) else 'REVISAR'
                if estado != 'OK':
                    fallos += 1
                vistos.add(rol)
                print(f'  {estado:7} {usuario:10} rol={rol:14} '
                      f'HTTP {respuesta.status} token={"si" if tiene_token else "no"} '
                      f'refresco={"si" if tiene_refresco else "no"}')
        except urllib.error.HTTPError as error:
            fallos += 1
            print(f'  FALLO   {usuario:10} HTTP {error.code} '
                  f'{error.read()[:80].decode("utf-8", "replace")}')
        except Exception as error:  # noqa: BLE001 - se informa y se sigue
            fallos += 1
            print(f'  FALLO   {usuario:10} {type(error).__name__}: {error}')

    print()
    print('Roles cubiertos ....', ', '.join(sorted(vistos)))
    if vistos != ESPERADOS:
        print('Faltan roles .......', ', '.join(sorted(ESPERADOS - vistos)) or 'ninguno')
    print('Resultado ..........', 'APROBADO' if fallos == 0 and vistos == ESPERADOS
          else f'REVISAR ({fallos} fallo(s))')
    return 0 if fallos == 0 and vistos == ESPERADOS else 1


if __name__ == '__main__':
    raise SystemExit(main())
