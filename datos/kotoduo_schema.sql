-- ============================================================
-- Kotoduo - Esquema de la base de datos estructurada (relacional)
-- Proyecto Integrado ES2 - Diseño de la solucion de software
-- Compatible con PostgreSQL (DDL de producción previsto) y
-- ejecutado en SQLite como evidencia funcional de la etapa de diseño.
-- ============================================================

PRAGMA foreign_keys = ON;

-- Roles: operario, encargado, vendedor, administrador
CREATE TABLE usuarios (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario       TEXT    NOT NULL UNIQUE,
    nombre        TEXT    NOT NULL,
    password_hash TEXT    NOT NULL,
    rol           TEXT    NOT NULL CHECK (rol IN ('operario','encargado','vendedor','administrador')),
    activo        INTEGER NOT NULL DEFAULT 1 CHECK (activo IN (0,1)),
    creado_en     TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- Secuencia de etapas configurable por tipo de trabajo (RNF-12)
CREATE TABLE etapas_definicion (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    tipo_trabajo TEXT   NOT NULL CHECK (tipo_trabajo IN ('uniforme','letrero','bordado_libre')),
    nombre       TEXT   NOT NULL,
    orden        INTEGER NOT NULL,
    area         TEXT   NOT NULL CHECK (area IN ('diseño','corte','confección','bordado','impresion','instalacion','terminaciones')),
    UNIQUE (tipo_trabajo, orden)
);

CREATE TABLE trabajos (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo          TEXT    NOT NULL UNIQUE,
    tipo_trabajo    TEXT    NOT NULL CHECK (tipo_trabajo IN ('uniforme','letrero','bordado_libre')),
    cliente_etiqueta TEXT   NOT NULL,          -- nombre a secas; sin contactos (RNF-08)
    pedido_ref      TEXT,                      -- referencia interna del pedido; NO almacena montos
    unidades        INTEGER NOT NULL CHECK (unidades > 0),
    medidas         TEXT    NOT NULL,
    estado_general  TEXT    NOT NULL DEFAULT 'en_producción'
                    CHECK (estado_general IN ('en_diseño','en_producción','detenido','terminado')),
    fecha_compromiso TEXT,
    creado_por      INTEGER NOT NULL REFERENCES usuarios(id),
    creado_en       TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE etapas_trabajo (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    trabajo_id     INTEGER NOT NULL REFERENCES trabajos(id) ON DELETE CASCADE,
    etapa_def_id   INTEGER NOT NULL REFERENCES etapas_definicion(id),
    estado         TEXT    NOT NULL DEFAULT 'pendiente'
                   CHECK (estado IN ('pendiente','en_curso','detenida','cerrada')),
    responsable_id INTEGER REFERENCES usuarios(id),
    fecha_inicio   TEXT,
    fecha_cierre   TEXT,
    notas          TEXT,
    UNIQUE (trabajo_id, etapa_def_id)
);

CREATE TABLE insumos (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre          TEXT    NOT NULL UNIQUE,
    unidad          TEXT    NOT NULL,
    stock_actual    REAL    NOT NULL CHECK (stock_actual >= 0),
    umbral_minimo   REAL    NOT NULL CHECK (umbral_minimo >= 0)
);

CREATE TABLE movimientos_insumo (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    insumo_id  INTEGER NOT NULL REFERENCES insumos(id),
    tipo       TEXT    NOT NULL CHECK (tipo IN ('ingreso','consumo')),
    cantidad   REAL    NOT NULL CHECK (cantidad > 0),
    trabajo_id INTEGER REFERENCES trabajos(id),
    usuario_id INTEGER NOT NULL REFERENCES usuarios(id),
    fecha      TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE alertas_insumo (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    insumo_id     INTEGER NOT NULL REFERENCES insumos(id),
    stock_momento REAL    NOT NULL,
    umbral_momento REAL   NOT NULL,
    avisado_a     TEXT    NOT NULL,
    estado        TEXT    NOT NULL DEFAULT 'activa' CHECK (estado IN ('activa','resuelta')),
    fecha         TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE aprobaciones_diseno (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    trabajo_id   INTEGER NOT NULL REFERENCES trabajos(id) ON DELETE CASCADE,
    version      INTEGER NOT NULL DEFAULT 1,
    estado       TEXT    NOT NULL DEFAULT 'pendiente'
                 CHECK (estado IN ('pendiente','aprobado','rechazado')),
    decidido_por INTEGER REFERENCES usuarios(id),
    comentarios  TEXT,
    fecha        TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE (trabajo_id, version)
);

CREATE TABLE bitacora (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id     INTEGER NOT NULL REFERENCES usuarios(id),
    accion         TEXT    NOT NULL,
    entidad        TEXT    NOT NULL,
    entidad_id     INTEGER,
    valor_anterior TEXT,
    valor_posterior TEXT,
    fecha          TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_etapas_trabajo_estado  ON etapas_trabajo(estado, responsable_id);
CREATE INDEX idx_trabajos_estado        ON trabajos(estado_general);
CREATE INDEX idx_bitacora_entidad       ON bitacora(entidad, entidad_id);
CREATE INDEX idx_mov_insumo             ON movimientos_insumo(insumo_id, fecha);
