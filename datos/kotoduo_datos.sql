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
  ('KTO-2026-016','bordado_libre','Deportes El Roble','PED-INT-79', 15, 'Escudo 15 cm',          'detenido',     '2026-11-13',2);

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
  (3,11,'detenida',3,'2026-10-24 08:00', NULL);

INSERT INTO insumos (nombre, unidad, stock_actual, umbral_minimo) VALUES
  ('Tinta sublimación negra','litros', 0.8, 2.0),
  ('Polos blancos M','unidades', 120, 40),
  ('Hilo poliester blanco','rollos', 6, 3);

INSERT INTO movimientos_insumo (insumo_id, tipo, cantidad, trabajo_id, usuario_id) VALUES
  (1,'consumo',0.6, 2, 3),
  (2,'consumo',40, 1, 3),
  (3,'ingreso', 4, NULL, 2);

INSERT INTO alertas_insumo (insumo_id, stock_momento, umbral_momento, avisado_a, estado, fecha) VALUES
  (1, 0.8, 2.0, 'encargado,vendedor', 'activa', '2026-10-24 09:10');

INSERT INTO aprobaciones_diseno (trabajo_id, version, estado, decidido_por, comentarios) VALUES
  (1, 1, 'aprobado',    4, 'Aprobado por el colegio; ajustar color de ribete.'),
  (2, 1, 'rechazado',   4, 'Letra muy fina para la distancia de lectura.'),
  (2, 2, 'aprobado',    4, 'Version con letra bold; conforme.'),
  (3, 1, 'pendiente',   NULL, NULL);

INSERT INTO bitacora (usuario_id, accion, entidad, entidad_id, valor_anterior, valor_posterior) VALUES
  (2,'crear','trabajos',1,NULL,'KTO-2026-014'),
  (4,'cambiar_estado','aprobaciones_diseno',2,'pendiente','rechazado'),
  (3,'cerrar_etapa','etapas_trabajo',1,'en_curso','cerrada');
