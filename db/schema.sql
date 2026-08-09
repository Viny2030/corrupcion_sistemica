-- ============================================================================
-- MAPA DE TRANSPARENCIA — Esquema PostgreSQL del grafo multipartito
-- Módulo Centralizado de Corrupción Sistémica
--
-- Modela los nodos (entidades) y aristas (relaciones) descritos en la
-- arquitectura de 4 capas: SNA, Finanzas Públicas, Conductual/Compliance
-- y Vaciamiento Institucional/Judicial.
-- Todas las tablas están pensadas para poblarse con DATOS REALES ingeridos
-- por los conectores en ingestion/. No hay datos sintéticos en este esquema.
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- ----------------------------------------------------------------------------
-- 1. ENTIDADES (nodos del grafo)
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS entidad (
    entidad_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tipo            VARCHAR(30) NOT NULL CHECK (tipo IN (
                        'EMPRESA', 'ORGANISMO_PUBLICO', 'FUNCIONARIO',
                        'DIPUTADO', 'SENADOR', 'JUEZ', 'FISCAL',
                        'BROKER', 'PARTIDO_POLITICO', 'OFFSHORE'
                    )),
    nombre          TEXT NOT NULL,
    identificador_fiscal VARCHAR(50),          -- CUIT/CUIL si aplica
    pais            VARCHAR(80),
    jurisdiccion    VARCHAR(120),              -- jurisdicción fiscal/legal (para módulo offshore)
    domicilio       TEXT,
    lat             DOUBLE PRECISION,          -- georreferenciación (PostGIS) para obra pública
    lon             DOUBLE PRECISION,
    metadata        JSONB DEFAULT '{}'::jsonb, -- campos flexibles por tipo de fuente
    fuente          VARCHAR(60) NOT NULL,      -- sensor de origen: TGN, COMPRAR, BORA, HCDN, SENADO, PJ, MEACI, etc.
    creado_en       TIMESTAMPTZ NOT NULL DEFAULT now(),
    actualizado_en  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_entidad_tipo ON entidad(tipo);
CREATE INDEX IF NOT EXISTS idx_entidad_fiscal ON entidad(identificador_fiscal);
CREATE INDEX IF NOT EXISTS idx_entidad_nombre_trgm ON entidad USING gin (nombre gin_trgm_ops);

-- Resolución de entidades: vínculos de "misma persona jurídica real" detectados
-- por fuzzy matching (domicilio, mail, directorio, apoderados, balances).
CREATE TABLE IF NOT EXISTS entidad_alias (
    id              BIGSERIAL PRIMARY KEY,
    entidad_id      UUID NOT NULL REFERENCES entidad(entidad_id),
    entidad_relacionada_id UUID NOT NULL REFERENCES entidad(entidad_id),
    metodo          VARCHAR(40) NOT NULL,   -- 'domicilio', 'email_pliego', 'directorio', 'representante_tecnico', 'balance'
    score_similitud NUMERIC(5,4) NOT NULL,  -- 0..1, salida de rapidfuzz / clustering
    evidencia       JSONB DEFAULT '{}'::jsonb,
    creado_en       TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (entidad_id, entidad_relacionada_id, metodo)
);

-- ----------------------------------------------------------------------------
-- 2. CONTRATACIONES PÚBLICAS (Compr.ar / Contrat.ar / BORA / TGN)
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS licitacion (
    licitacion_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    fuente_id_externo   VARCHAR(120),          -- id en Compr.ar/Contrat.ar/BORA
    organismo_id        UUID NOT NULL REFERENCES entidad(entidad_id),
    objeto              TEXT,
    rubro               VARCHAR(120),
    presupuesto_oficial NUMERIC(18,2),
    fecha_apertura      DATE,
    fecha_adjudicacion  DATE,
    monto_adjudicado    NUMERIC(18,2),
    monto_ejecutado_final NUMERIC(18,2),       -- para low-balling index
    modalidad           VARCHAR(60),           -- licitación pública, contratación directa, etc.
    metadata            JSONB DEFAULT '{}'::jsonb,
    fuente              VARCHAR(60) NOT NULL,
    creado_en            TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS oferta (
    oferta_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    licitacion_id   UUID NOT NULL REFERENCES licitacion(licitacion_id),
    empresa_id      UUID NOT NULL REFERENCES entidad(entidad_id),
    monto_ofertado  NUMERIC(18,2),
    porcentaje_sobre_ganadora NUMERIC(8,4),  -- calculado: (monto - monto_ganador) / monto_ganador
    resultado       VARCHAR(20) CHECK (resultado IN ('GANADORA', 'PERDEDORA', 'DESCALIFICADA')),
    creado_en       TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (licitacion_id, empresa_id)
);

CREATE INDEX IF NOT EXISTS idx_oferta_empresa ON oferta(empresa_id);
CREATE INDEX IF NOT EXISTS idx_oferta_licitacion ON oferta(licitacion_id);

CREATE TABLE IF NOT EXISTS adenda (
    adenda_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    licitacion_id   UUID NOT NULL REFERENCES licitacion(licitacion_id),
    fecha           DATE,
    monto_original  NUMERIC(18,2),
    monto_nuevo     NUMERIC(18,2),
    motivo          TEXT,
    creado_en       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS pago_tgn (
    pago_id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    licitacion_id       UUID REFERENCES licitacion(licitacion_id),
    empresa_id          UUID NOT NULL REFERENCES entidad(entidad_id),
    organismo_id        UUID NOT NULL REFERENCES entidad(entidad_id),
    fecha_factura       DATE,
    fecha_pago          DATE,
    dias_habiles_pago   INTEGER,              -- calculado
    monto               NUMERIC(18,2),
    creado_en           TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ----------------------------------------------------------------------------
-- 3. FINANCIAMIENTO POLÍTICO Y ROI
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS aporte_campana (
    aporte_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    aportante_id    UUID NOT NULL REFERENCES entidad(entidad_id),
    partido_id      UUID NOT NULL REFERENCES entidad(entidad_id),
    eleccion        VARCHAR(60),   -- ej. 'Legislativas 2025'
    monto           NUMERIC(18,2),
    fecha           DATE,
    fuente          VARCHAR(60) NOT NULL,  -- ej. Cámara Nacional Electoral
    creado_en       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ----------------------------------------------------------------------------
-- 4. ACTIVIDAD LEGISLATIVA (HCDN / Senado)
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS votacion (
    votacion_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    camara          VARCHAR(20) CHECK (camara IN ('DIPUTADOS', 'SENADORES')),
    expediente      VARCHAR(80),
    titulo          TEXT,
    fecha           DATE,
    resultado       VARCHAR(30),
    fuente          VARCHAR(60) NOT NULL,
    creado_en       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS voto_individual (
    id              BIGSERIAL PRIMARY KEY,
    votacion_id     UUID NOT NULL REFERENCES votacion(votacion_id),
    legislador_id   UUID NOT NULL REFERENCES entidad(entidad_id),
    voto            VARCHAR(20) CHECK (voto IN ('AFIRMATIVO', 'NEGATIVO', 'ABSTENCION', 'AUSENTE'))
);

-- ----------------------------------------------------------------------------
-- 5. PODER JUDICIAL
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS causa_judicial (
    causa_id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    caratula             TEXT,
    fuero                VARCHAR(80),
    jurisdiccion         VARCHAR(80),
    fecha_inicio         DATE,
    fecha_resolucion     DATE,
    estado               VARCHAR(40),  -- 'EN_TRAMITE', 'PRESCRIPTA', 'CONDENA', 'ABSOLUCION', 'SOBRESEIMIENTO'
    texto_fallo           TEXT,         -- para NLP judicial
    juez_id               UUID REFERENCES entidad(entidad_id),
    fuente                VARCHAR(60) NOT NULL,
    creado_en             TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS imputado (
    id              BIGSERIAL PRIMARY KEY,
    causa_id        UUID NOT NULL REFERENCES causa_judicial(causa_id),
    entidad_id      UUID NOT NULL REFERENCES entidad(entidad_id),
    rango_jerarquico VARCHAR(40),  -- 'ALTO_MANDO', 'MEDIO', 'BAJO' — para sesgo de sanción
    condena_meses    INTEGER,
    monto_multa      NUMERIC(18,2)
);

-- ----------------------------------------------------------------------------
-- 6. COMPLIANCE / MEACI
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS auditoria_compliance (
    auditoria_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    empresa_id      UUID NOT NULL REFERENCES entidad(entidad_id),
    fecha           DATE,
    tiene_programa_integridad BOOLEAN,
    score_efectividad NUMERIC(5,2),  -- 0-100, evaluación real del programa (no solo declarativo)
    hallazgos       JSONB DEFAULT '{}'::jsonb,
    fuente          VARCHAR(60) NOT NULL DEFAULT 'MEACI'
);

-- ----------------------------------------------------------------------------
-- 7. GRAFO — ARISTAS GENÉRICAS (para export a Neo4j/GraphML)
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS grafo_arista (
    arista_id       BIGSERIAL PRIMARY KEY,
    origen_id        UUID NOT NULL REFERENCES entidad(entidad_id),
    destino_id       UUID NOT NULL REFERENCES entidad(entidad_id),
    tipo_relacion    VARCHAR(40) NOT NULL,  -- 'ADJUDICACION','CO_PRESENTISMO','APORTE','VOTO_FAVORABLE','INTERMEDIACION', etc.
    peso             NUMERIC(12,4) DEFAULT 1.0,
    metadata         JSONB DEFAULT '{}'::jsonb,
    creado_en        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_arista_origen ON grafo_arista(origen_id);
CREATE INDEX IF NOT EXISTS idx_arista_destino ON grafo_arista(destino_id);
CREATE INDEX IF NOT EXISTS idx_arista_tipo ON grafo_arista(tipo_relacion);

-- ----------------------------------------------------------------------------
-- 8. INDICADORES MACRO (CPI / WGI) — series reales por país/año
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS indicador_macro (
    id              BIGSERIAL PRIMARY KEY,
    pais_iso3       VARCHAR(3) NOT NULL,
    anio            INTEGER NOT NULL,
    indicador       VARCHAR(40) NOT NULL,  -- 'CPI' | 'WGI_CONTROL_CORRUPCION' | 'WGI_RULE_OF_LAW' ...
    valor           NUMERIC(10,4),
    fuente          VARCHAR(60) NOT NULL,
    UNIQUE (pais_iso3, anio, indicador)
);

-- ----------------------------------------------------------------------------
-- 9. SCORING DE RIESGO SISTÉMICO (salida del motor, con desglose XAI)
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS score_riesgo (
    score_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entidad_id       UUID REFERENCES entidad(entidad_id),
    licitacion_id    UUID REFERENCES licitacion(licitacion_id),
    capa             VARCHAR(20) NOT NULL,  -- 'SNA','FINANZAS','CONDUCTUAL','JUDICIAL','TOTAL'
    score            NUMERIC(6,2) NOT NULL, -- 0-100
    desglose         JSONB NOT NULL,        -- audit card: {"HHI_ELEVADO": 30, "ADENDAS_REPETIDAS": 25, ...}
    calculado_en     TIMESTAMPTZ NOT NULL DEFAULT now()
);
