-- Datos de ejemplo coherentes con el caso Kotoduo (sin montos ni contactos)
INSERT INTO usuarios (usuario, nombre, password_hash, rol) VALUES
  ('aeo',   'Cesar Aedo',        '$argon2id$v=19$m=65536,t=3,p=4$placeholder$hash', 'administrador'),
  ('bjaque','Benjamin Jaque',    '$argon2id$v=19$m=65536,t=3,p=4$placeholder$hash', 'encargado'),
  ('msanchez','Mariana Soto',    '$argon2id$v=19$m=65536,t=3,p=4$placeholder$hash', 'operario'),
  ('jrojas','Jorge Rojas',       '$argon2id$v=19$m=65536,t=3,p=4$placeholder$hash', 'vendedor');

INSERT INTO etapas_definicion (tipo_trabajo, nombre, orden, area) VALUES
  ('uniforme','Diseño y aprobación', 1,'diseño'),
  ('uniforme','Corte',               2,'corte'),
  ('uniforme','Confección',          3,'confección'),
  ('uniforme','Bordado',             4,'bordado'),
  ('uniforme','Terminaciones',       5,'terminaciones'),
  ('letrero','Diseño y aprobación',  1,'diseño'),
  ('letrero','Material',             2,'corte'),
  ('letrero','Grabado',              3,'impresion'),
  ('letrero','Instalacion',          4,'instalacion'),
  ('bordado_libre','Diseño y aprobación',1,'diseño'),
  ('bordado_libre','Bordado',             2,'bordado');

INSERT INTO trabajos (codigo, tipo_trabajo, cliente_etiqueta, pedido_ref, unidades, medidas, estado_general, fecha_compromiso, creado_por) VALUES
  ('KTO-2026-014','uniforme',    'Colegio San Ignacio','PED-INT-77', 40, 'Pecho 28 cm, manga 18 cm','en_producción','2026-11-06',2),
  ('KTO-2026-015','letrero',     'Clinica Los Alerces','PED-INT-78',  2, '120 x 40 cm',           'en_producción','2026-11-10',2),
  ('KTO-2026-016','bordado_libre','Deportes El Roble','PED-INT-79', 15, 'Escudo 15 cm',          'detenido',     '2026-11-13',2),
  ('KTO-2026-017','uniforme',    'Academia Cordillera','PED-INT-80', 30, 'Pecho 25 cm, manga 16 cm','en_diseño',   '2026-11-27',2),
  ('KTO-2026-018','letrero',     'Ferreteria El Molino','PED-INT-81', 1, '80 x 30 cm',            'en_diseño',    '2026-11-30',2),
  ('KTO-2026-019','uniforme',    'Escuela Basica Los Coihues','PED-INT-82', 55, 'Pecho 30 cm, manga 20 cm','en_producción','2026-11-25',2),
  ('KTO-2026-020','letrero',     'Cafe Terminal','PED-INT-83',          2, '100 x 35 cm',           'en_producción','2026-11-26',2),
  ('KTO-2026-021','bordado_libre','Club Deportivo Trumao','PED-INT-84',12, 'Escudo 12 cm',          'detenido',     '2026-11-24',2),
  ('KTO-2026-022','uniforme',    'Constructora Sur','PED-INT-85',      25, 'Pecho 28 cm, manga 18 cm','terminado',   '2026-11-20',2),
  ('KTO-2026-023','letrero',     'Farmacia San Martin','PED-INT-86',    1, '60 x 25 cm',            'terminado',    '2026-11-18',2),
  ('KTO-2026-024','bordado_libre','Academia de Danza Aysen','PED-INT-87',18,'Inicial 10 cm',        'terminado',    '2026-11-21',2);

INSERT INTO etapas_trabajo (trabajo_id, etapa_def_id, estado, responsable_id, fecha_inicio, fecha_cierre) VALUES
  (1,1,'cerrada', 4, '2026-10-21 09:00','2026-10-21 12:30'),
  (1,2,'cerrada', 3, '2026-10-22 08:30','2026-10-22 11:00'),
  (1,3,'en_curso',3, '2026-10-23 08:15', NULL),
  (1,4,'pendiente',NULL, NULL, NULL),
  (1,5,'pendiente',NULL, NULL, NULL),
  (2,6,'cerrada', 4, '2026-10-22 14:00','2026-10-22 17:00'),
  (2,7,'en_curso',3, '2026-10-23 09:00', NULL),
  (2,8,'pendiente',NULL, NULL, NULL),
  (2,9,'pendiente',NULL, NULL, NULL),
  (3,10,'cerrada',4, '2026-10-23 10:00','2026-10-23 15:00'),
  (3,11,'detenida',3,'2026-10-24 08:00', NULL),
  (4,1,'en_curso', NULL,'2026-11-24 09:00', NULL),
  (4,2,'pendiente',NULL, NULL, NULL),
  (4,3,'pendiente',NULL, NULL, NULL),
  (4,4,'pendiente',NULL, NULL, NULL),
  (4,5,'pendiente',NULL, NULL, NULL),
  (5,6,'en_curso', NULL,'2026-11-25 10:30', NULL),
  (5,7,'pendiente',NULL, NULL, NULL),
  (5,8,'pendiente',NULL, NULL, NULL),
  (5,9,'pendiente',NULL, NULL, NULL),
  (6,1,'cerrada', 4, '2026-11-17 09:00','2026-11-17 12:00'),
  (6,2,'cerrada', 3, '2026-11-18 08:30','2026-11-18 11:30'),
  (6,3,'en_curso',3, '2026-11-23 08:15', NULL),
  (6,4,'pendiente',NULL, NULL, NULL),
  (6,5,'pendiente',NULL, NULL, NULL),
  (7,6,'cerrada', 4, '2026-11-18 14:00','2026-11-18 17:00'),
  (7,7,'cerrada', 3, '2026-11-19 09:00','2026-11-19 15:00'),
  (7,8,'en_curso',3, '2026-11-23 09:00', NULL),
  (7,9,'pendiente',NULL, NULL, NULL),
  (8,10,'cerrada',4, '2026-11-19 10:00','2026-11-19 16:00'),
  (8,11,'detenida',3,'2026-11-21 08:00', NULL),
  (9,1,'cerrada', 4, '2026-11-10 09:00','2026-11-10 12:00'),
  (9,2,'cerrada', 3, '2026-11-11 08:30','2026-11-11 11:00'),
  (9,3,'cerrada', 3, '2026-11-12 08:00','2026-11-14 17:00'),
  (9,4,'cerrada', 3, '2026-11-15 08:30','2026-11-16 12:30'),
  (9,5,'cerrada', 3, '2026-11-17 09:00','2026-11-17 16:00'),
  (10,6,'cerrada',4, '2026-11-09 14:00','2026-11-09 17:00'),
  (10,7,'cerrada',3, '2026-11-10 09:00','2026-11-11 15:00'),
  (10,8,'cerrada',3, '2026-11-12 09:00','2026-11-13 16:00'),
  (10,9,'cerrada',3, '2026-11-14 10:00','2026-11-14 15:00'),
  (11,10,'cerrada',4,'2026-11-12 10:00','2026-11-12 16:00'),
  (11,11,'cerrada',3,'2026-11-13 09:00','2026-11-13 12:00');

INSERT INTO insumos (nombre, unidad, stock_actual, umbral_minimo) VALUES
  ('Tinta sublimación negra','litros', 0.8, 2.0),
  ('Polos blancos M','unidades', 120, 40),
  ('Hilo poliester blanco','rollos', 6, 3),
  ('Vinil adhesivo blanco','metros', 4, 15),
  ('Bobina de transfer tamaño carta','unidades', 2, 8);

INSERT INTO movimientos_insumo (insumo_id, tipo, cantidad, trabajo_id, usuario_id) VALUES
  (1,'consumo',0.6, 2, 3),
  (2,'consumo',40, 1, 3),
  (3,'ingreso', 4, NULL, 2),
  (4,'consumo', 11, 2, 3),
  (5,'consumo', 6, 5, 3);

INSERT INTO alertas_insumo (insumo_id, stock_momento, umbral_momento, avisado_a, estado, fecha) VALUES
  (1, 0.8, 2.0, 'encargado,vendedor', 'activa', '2026-10-24 09:10'),
  (4, 4, 15, 'encargado', 'activa', '2026-11-20 08:45'),
  (5, 2, 8, 'encargado,vendedor', 'activa', '2026-11-23 16:20');

INSERT INTO aprobaciones_diseno (trabajo_id, version, estado, decidido_por, comentarios) VALUES
  (1, 1, 'aprobado',    4, 'Aprobado por el colegio; ajustar color de ribete.'),
  (2, 1, 'rechazado',   4, 'Letra muy fina para la distancia de lectura.'),
  (2, 2, 'aprobado',    4, 'Version con letra bold; conforme.'),
  (3, 1, 'pendiente',   NULL, NULL),
  (4, 1, 'pendiente',   NULL, NULL),
  (5, 1, 'pendiente',   NULL, NULL),
  (6, 1, 'aprobado',    4, 'Diseno aprobado; se inicia el corte.'),
  (7, 1, 'aprobado',    4, 'Aprobado con letra reforzada para la distancia.'),
  (8, 1, 'aprobado',    4, 'Escudo aprobado en version final.'),
  (9, 1, 'aprobado',    4, 'Modelo conforme; colores revisados.'),
  (10,1, 'aprobado',    4, 'Letra bold acordada con el cliente.'),
  (11,1, 'aprobado',    4, 'Escudo bordado aprobado en prueba.');

INSERT INTO bitacora (usuario_id, accion, entidad, entidad_id, valor_anterior, valor_posterior) VALUES
  (2,'crear','trabajos',1,NULL,'KTO-2026-014'),
  (4,'cambiar_estado','aprobaciones_diseno',2,'pendiente','rechazado'),
  (3,'cerrar_etapa','etapas_trabajo',1,'en_curso','cerrada'),
  (2,'crear','trabajos',4,NULL,'KTO-2026-017'),
  (2,'crear','trabajos',6,NULL,'KTO-2026-019'),
  (4,'cambiar_estado','aprobaciones_diseno',7,'pendiente','aprobado'),
  (3,'cerrar_etapa','etapas_trabajo',22,'en_curso','cerrada'),
  (2,'crear','trabajos',9,NULL,'KTO-2026-022'),
  (3,'cambiar_estado','trabajos',9,'en_producción','terminado');
