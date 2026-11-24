# -*- coding: utf-8 -*-
"""Ejecuta DDL + datos + consultas en SQLite y captura la salida como evidencia."""
import sqlite3, io, sys, os, datetime
from argon2 import PasswordHasher

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
BASE = os.path.dirname(os.path.abspath(__file__))
# KOTODUO_DB permite apuntar a otra base (p. ej. una copia de prueba en el
# servidor) sin modificar este script.
DB = os.environ.get('KOTODUO_DB') or os.path.join(BASE, 'kotoduo.db')

# Cuentas semilla con hash argon2id real. Las contraseñas no están en el
# código: se leen de api/credenciales_semilla.txt (fuera del repositorio).
from semilla_cuentas import cargar_semilla   # noqa: E402

ph = PasswordHasher()
CLAVES = {usuario: datos['clave']
          for usuario, datos in cargar_semilla().items()}

if os.path.exists(DB):
    os.remove(DB)

conn = sqlite3.connect(DB)
conn.execute('PRAGMA foreign_keys = ON')
cur = conn.cursor()

out_ddl = io.StringIO()
out_ddl.write(f'Ejecución: {datetime.datetime.now():%d-%m-%Y %H:%M}\n')
out_ddl.write('SQLite %s\n\n' % sqlite3.sqlite_version)

for fname, label in (('kotoduo_schema.sql', 'DDL (esquema)'),
                     ('kotoduo_datos.sql', 'Datos de ejemplo')):
    sql = open(os.path.join(BASE, fname), encoding='utf-8').read()
    if fname == 'kotoduo_datos.sql':
        for usuario, clave in CLAVES.items():
            marcador = f"'{usuario}'"
            if marcador not in sql:
                continue   # cuenta de la semilla sin fila en los datos
            pos = sql.index(marcador)
            fin = sql.index("'$argon2id$v=19$m=65536,t=3,p=4$placeholder$hash'", pos)
            sql = (sql[:fin] + f"'{ph.hash(clave)}'" + sql[fin + len("'$argon2id$v=19$m=65536,t=3,p=4$placeholder$hash'"):])
    out_ddl.write(f'===== {label}: {fname} =====\n')
    cur.executescript(sql)
    conn.commit()
    out_ddl.write('OK - ejecutado sin errores\n\n')

cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
tablas = [r[0] for r in cur.fetchall()]
out_ddl.write('Tablas creadas: ' + ', '.join(tablas) + '\n\n')
for t in tablas:
    info = cur.execute(f'PRAGMA table_info({t})').fetchall()
    fks = cur.execute(f'PRAGMA foreign_key_list({t})').fetchall()
    out_ddl.write(f'{t}: {len(info)} columnas'
                  + (f', {len(fks)} FK' if fks else '') + '\n')
cur.execute('SELECT COUNT(*) FROM sqlite_master WHERE type="index"')
out_ddl.write(f'Indices: {cur.fetchone()[0]}\n')

# prueba de integridad referencial: intento de FK invalida
out_ddl.write('\n===== Prueba de integridad referencial =====\n')
try:
    cur.execute("INSERT INTO etapas_trabajo (trabajo_id, etapa_def_id) VALUES (999, 1)")
    out_ddl.write('FALLO: aceptó FK invalida\n')
except sqlite3.IntegrityError as e:
    out_ddl.write(f'FK inválida rechazada -> {e}\n')
try:
    cur.execute("UPDATE trabajos SET unidades = 0 WHERE id = 1")
    out_ddl.write('FALLO: aceptó unidades <= 0\n')
except sqlite3.IntegrityError as e:
    out_ddl.write(f'CHECK unidades > 0 rechazado -> {e}\n')
conn.rollback()

open(os.path.join(BASE, 'salida_ddl.txt'), 'w', encoding='utf-8').write(out_ddl.getvalue())

out_q = io.StringIO()
out_q.write(f'Ejecución de consultas: {datetime.datetime.now():%d-%m-%Y %H:%M}\n\n')
sql_all = open(os.path.join(BASE, 'consultas.sql'), encoding='utf-8').read()
bloques, actual, dentro = [], [], False
for linea in sql_all.splitlines():
    if linea.strip().startswith('-- CQ-'):
        if actual:
            bloques.append('\n'.join(actual))
        actual, dentro = [linea], True
    elif dentro:
        actual.append(linea)
if actual:
    bloques.append('\n'.join(actual))

for b in bloques:
    cab = b.splitlines()[0].replace('-- ', '')
    consulta = '\n'.join(l for l in b.splitlines() if not l.strip().startswith('--'))
    out_q.write(f'===== {cab} =====\n')
    cur.execute(consulta)
    cols = [d[0] for d in cur.description]
    filas = cur.fetchall()
    out_q.write(' | '.join(cols) + '\n')
    for f in filas:
        out_q.write(' | '.join('NULL' if v is None else str(v) for v in f) + '\n')
    out_q.write(f'({len(filas)} filas)\n\n')

open(os.path.join(BASE, 'salida_consultas.txt'), 'w', encoding='utf-8').write(out_q.getvalue())
conn.close()
print(out_ddl.getvalue())
print(out_q.getvalue())
