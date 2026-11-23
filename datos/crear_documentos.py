# -*- coding: utf-8 -*-
"""Base de datos no estructurada (documental) con TinyDB.

Almacena las fichas de diseño de cada trabajo: variantes, paleta de colores,
ruta del archivo gráfico y notas de aprobación. Es información jerárquica
y variable (cada diseño tiene distinta cantidad de variantes y campos extra),
por eso no se fuerza a un esquema relacional.
"""
import io, sys, os, datetime
from tinydb import TinyDB, Query

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
BASE = os.path.dirname(os.path.abspath(__file__))
# KOTODUO_DOC_DB permite apuntar a otra ficha documental (copia de prueba).
DBPATH = os.environ.get('KOTODUO_DOC_DB') or os.path.join(BASE, 'documentos.json')

db = TinyDB(DBPATH)
disenos = db.table('disenos')

disenos.truncate()

# Alta de un documento (operación de almacenamiento)
disenos.insert({
    'trabajo_codigo': 'KTO-2026-014',
    'version': 1,
    'archivo': 'diseños/KTO-2026-014/v1_escudo.svg',
    'formato': 'svg',
    'paleta': ['azul marino', 'blanco', 'gris'],
    'variantes': [
        {'nombre': 'frontal',   'medidas': '28x18 cm', 'archivo': 'v1_frontal.svg'},
        {'nombre': 'manga_izq', 'medidas': '8x8 cm',   'archivo': 'v1_manga.svg'},
    ],
    'observaciones': ['Cliente pidió bajar el ribete 2 mm'],
    'aprobado': True,
    'decidido_por': 'jrojas',
    'fecha': '2026-10-21 12:30',
})

disenos.insert({
    'trabajo_codigo': 'KTO-2026-015',
    'version': 2,
    'archivo': 'diseños/KTO-2026-015/v2_letrero.pdf',
    'formato': 'pdf',
    'paleta': ['negro', 'blanco'],
    'variantes': [
        {'nombre': 'letra_bold', 'medidas': '120x40 cm', 'archivo': 'v2_letra.pdf'},
    ],
    'observaciones': ['v1 rechazada por grosor de letra', 'v2 con tipografía bold'],
    'aprobado': True,
    'decidido_por': 'jrojas',
    'fecha': '2026-10-23 10:05',
})

disenos.insert({
    'trabajo_codigo': 'KTO-2026-016',
    'version': 1,
    'archivo': 'diseños/KTO-2026-016/v1_escudo_bordado.png',
    'formato': 'png',
    'paleta': ['verde', 'amarillo'],
    'variantes': [
        {'nombre': 'escudo', 'medidas': '15x15 cm', 'archivo': 'v1_escudo.png'},
        {'nombre': 'nombre', 'medidas': '12x3 cm',  'archivo': 'v1_nombre.png'},
    ],
    'observaciones': [],
    'aprobado': False,
    'decidido_por': None,
    'fecha': '2026-10-24 09:40',
})

Q = Query()
out = io.StringIO()
out.write(f'Base documental TinyDB: {DBPATH}\n')
out.write(f'Documentos almacenados: {len(disenos)}\n\n')

out.write('===== BQ-01: diseño aprobado de un trabajo (consulta por ruta) =====\n')
doc = disenos.search((Q.trabajo_codigo == 'KTO-2026-015') & (Q.aprobado == True))[0]
out.write(f"{doc['trabajo_codigo']} v{doc['version']}: {doc['archivo']} "
          f"({len(doc['variantes'])} variante(s))\n\n")

out.write('===== BQ-02: variantes con medidas exactas "15x15 cm" (búsqueda en subdocumentos) =====\n')
for d in disenos.search(Q.variantes.any(Q.medidas == '15x15 cm')):
    for v in d['variantes']:
        if v['medidas'] == '15x15 cm':
            out.write(f"{d['trabajo_codigo']}: {v['nombre']} {v['medidas']}\n")
out.write('\n')

out.write('===== BQ-03: proyección ligera (códigos, versión y aprobación) =====\n')
for d in disenos.all():
    out.write(f"{d['trabajo_codigo']} v{d['version']} aprobado={d['aprobado']}\n")
out.write('\n')

out.write('===== BQ-04: actualización de un campo (operación de modificación) =====\n')
disenos.update({'aprobado': True, 'decidido_por': 'jrojas',
                'observaciones': ['Aprobado en reunión del 24-10']},
               (Q.trabajo_codigo == 'KTO-2026-016'))
d = disenos.get(Q.trabajo_codigo == 'KTO-2026-016')
out.write(f"{d['trabajo_codigo']}: aprobado={d['aprobado']} por {d['decidido_por']}\n")

open(os.path.join(BASE, 'salida_documentos.txt'), 'w', encoding='utf-8').write(out.getvalue())
db.close()
print(out.getvalue())
