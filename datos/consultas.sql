-- ============================================================
-- Consultas de ejemplo (evidencia funcional de la base estructurada)
-- ============================================================

-- CQ-01: siguiente actividad abierta de cada trabajo en producción
--        (HU-05 / RF-05: cola de trabajo por area)
SELECT t.codigo, ed.nombre AS siguiente_etapa, ed.area,
       u.nombre AS responsable
FROM trabajos t
JOIN etapas_trabajo et ON et.trabajo_id = t.id
JOIN etapas_definicion ed ON ed.id = et.etapa_def_id
LEFT JOIN usuarios u ON u.id = et.responsable_id
WHERE t.estado_general = 'en_producción'
  AND et.estado IN ('pendiente','en_curso')
ORDER BY t.codigo, ed.orden;

-- CQ-02: tablero general (HU-05 / RF-08)
SELECT estado_general, COUNT(*) AS trabajos
FROM trabajos
GROUP BY estado_general;

-- CQ-03: insumos bajo el umbral minimo (RF-06)
SELECT i.nombre, i.stock_actual, i.umbral_minimo
FROM insumos i
WHERE i.stock_actual < i.umbral_minimo;

-- CQ-04: trabajos cuya aprobación de diseño quedo rechazada y su version vigente (RF-07)
SELECT t.codigo, ad.version, ad.estado, ad.comentarios
FROM aprobaciones_diseno ad
JOIN trabajos t ON t.id = ad.trabajo_id
WHERE ad.estado = 'rechazado'
   OR ad.version = (SELECT MAX(version) FROM aprobaciones_diseno x WHERE x.trabajo_id = t.id)
ORDER BY t.codigo, ad.version;

-- CQ-05: bitacora de una entidad concreta (RF-11)
SELECT b.fecha, u.nombre, b.accion, b.entidad,
       b.valor_anterior, b.valor_posterior
FROM bitacora b
JOIN usuarios u ON u.id = b.usuario_id
WHERE b.entidad = 'trabajos' AND b.entidad_id = 1
ORDER BY b.fecha;

-- CQ-06: consumo de insumos por trabajo (trazabilidad producción -> insumos)
SELECT t.codigo, i.nombre, SUM(m.cantidad) AS consumido
FROM movimientos_insumo m
JOIN insumos i ON i.id = m.insumo_id
JOIN trabajos t ON t.id = m.trabajo_id
WHERE m.tipo = 'consumo'
GROUP BY t.codigo, i.nombre;
