-- Capa raw: los datos tal como llegan de la fuente, sin tipar.
-- Idempotente: se puede ejecutar sobre una base ya inicializada.

create schema if not exists raw;

-- Descarga masiva mensual. El CSV trae una fila por licitación × ítem × oferta y
-- ~85 de sus ~110 columnas son constantes por licitación, así que se guarda sin
-- pérdida en dos tablas:
--   bulk_licitacion: la primera fila de cada CodigoExterno, completa.
--   bulk_fila:       cada fila del CSV, solo con las columnas que difieren de esa
--                    primera fila (vacía para la propia primera fila).
-- La fila original es `l.data || f.data` (vista raw.bulk_fila_completa).
-- Cada mes se reemplaza completo en una transacción: no hay clave natural de fila.
create table if not exists raw.bulk_licitacion (
    source_month   text        not null,  -- AAAA-M, como lo publica ChileCompra
    codigo_externo text        not null,
    data           jsonb       not null,  -- columnas del CSV como texto ('NA' → null)
    extracted_at   timestamptz not null,
    primary key (source_month, codigo_externo)
);
create index if not exists bulk_licitacion_codigo_idx on raw.bulk_licitacion (codigo_externo);

create table if not exists raw.bulk_fila (
    source_month   text    not null,
    row_num        integer not null,  -- posición en el CSV, desde 1
    codigo_externo text    not null,
    data           jsonb   not null,
    primary key (source_month, row_num)
);
create index if not exists bulk_fila_codigo_idx on raw.bulk_fila (source_month, codigo_externo);

create or replace view raw.bulk_fila_completa as
select f.source_month, f.row_num, f.codigo_externo, l.data || f.data as data, l.extracted_at
from raw.bulk_fila f
join raw.bulk_licitacion l using (source_month, codigo_externo);

-- Detalle de la API: una fila por licitación, siempre la última versión.
create table if not exists raw.api_licitacion (
    codigo_externo text primary key,
    data           jsonb       not null,  -- elemento de Listado[] tal cual
    extracted_at   timestamptz not null
);

-- Bitácora de extracciones: permite reanudar y saber qué está cargado.
create table if not exists raw.extraction_log (
    id             bigserial primary key,
    source         text        not null,  -- 'bulk' | 'api_listing'
    key            text        not null,  -- mes AAAA-M o fecha AAAA-MM-DD
    status         text        not null,  -- 'ok' | 'error'
    rows           integer,
    remote_version text,                  -- Last-Modified de la descarga masiva
    error          text,                  -- error, o nota en una carga ok (p. ej. registros descartados)
    started_at     timestamptz not null default now(),
    finished_at    timestamptz
);
create index if not exists extraction_log_key_idx on raw.extraction_log (source, key, finished_at desc);
