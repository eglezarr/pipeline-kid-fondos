-- Modelo de datos de los KID en PostgreSQL (Aurora).
-- La etapa 4 aplica este fichero al empezar cada carga: todas las sentencias son idempotentes.
-- La carga quita los comentarios y separa las sentencias por punto y coma.

-- Un PDF por fila, identificado por su huella sha256: si una ejecución vuelve a descargar el mismo
-- documento, no se crea una fila nueva, solo se actualiza la fecha de la última descarga.
CREATE TABLE IF NOT EXISTS documentos (
    id               BIGSERIAL   PRIMARY KEY,
    sha256           CHAR(64)    NOT NULL UNIQUE,
    gestora          TEXT        NOT NULL,  -- fuente de la captura: bestinver, azvalor
    slug             TEXT        NOT NULL,  -- identificador del fondo en la web de la gestora
    fondo_web        TEXT,                  -- nombre del fondo en la web
    url_ficha        TEXT,                  -- página del fondo donde está el enlace al KID
    url_origen       TEXT        NOT NULL,  -- URL del PDF
    isin_web         CHAR(12),              -- ISIN publicado en la ficha, si es único
    clave_s3         TEXT        NOT NULL,  -- PDF en S3 (primera captura)
    tamano_bytes     INTEGER,
    primera_descarga TIMESTAMPTZ NOT NULL,
    ultima_descarga  TIMESTAMPTZ NOT NULL
);

-- Datos extraídos de cada documento (Anexo A), con la trazabilidad de la extracción.
CREATE TABLE IF NOT EXISTS kid (
    id                          BIGSERIAL    PRIMARY KEY,
    documento_id                BIGINT       NOT NULL UNIQUE REFERENCES documentos (id) ON DELETE CASCADE,
    isin                        CHAR(12)     NOT NULL,
    nombre_producto             TEXT         NOT NULL,
    nombre_clase                TEXT,
    gestora                     TEXT         NOT NULL,  -- productor del PRIIP según el KID
    fecha_documento             DATE,
    sri                         SMALLINT     NOT NULL CHECK (sri BETWEEN 1 AND 7),
    periodo_mantenimiento_anios NUMERIC(5, 2),
    gastos_corrientes_pct       NUMERIC(6, 3),
    costes_entrada_pct          NUMERIC(6, 3),
    costes_salida_pct           NUMERIC(6, 3),
    modelo                      TEXT         NOT NULL,  -- modelo de Bedrock que hizo la extracción
    fecha_extraccion            TIMESTAMPTZ  NOT NULL,
    evidencias                  JSONB        NOT NULL,  -- fragmento literal de cada campo
    verificacion_evidencias     JSONB        NOT NULL,  -- si cada evidencia aparece en el documento
    validaciones                JSONB        NOT NULL,  -- ISIN válido, coincide con la web, SRI en rango
    cargado                     TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS kid_isin ON kid (isin);

-- Versión más reciente de cada ISIN: la que consultan la API y la aplicación.
DROP VIEW IF EXISTS kid_actual;

CREATE VIEW kid_actual AS
SELECT DISTINCT ON (k.isin)
       k.isin,
       k.nombre_producto,
       k.nombre_clase,
       k.gestora,
       d.gestora AS fuente,
       k.fecha_documento,
       k.sri,
       k.periodo_mantenimiento_anios,
       k.gastos_corrientes_pct,
       k.costes_entrada_pct,
       k.costes_salida_pct,
       k.validaciones,
       k.verificacion_evidencias,
       k.evidencias,
       k.modelo,
       k.fecha_extraccion,
       d.id AS documento_id,
       d.url_origen,
       d.url_ficha,
       d.clave_s3,
       d.primera_descarga,
       d.ultima_descarga
  FROM kid k
  JOIN documentos d ON d.id = k.documento_id
 ORDER BY k.isin, k.fecha_documento DESC NULLS LAST, d.ultima_descarga DESC;
