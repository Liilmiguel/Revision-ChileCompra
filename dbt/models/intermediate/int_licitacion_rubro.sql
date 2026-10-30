{{ config(indexes=[{'columns': ['codigo_externo']}]) }}

-- Rubros (niveles 1 y 2 de la clasificación de ChileCompra, basada en UNSPSC) de cada
-- licitación, con cuántas de sus líneas caen en cada uno. Una licitación puede tener
-- varios: el filtro por rubro de la versión web la incluye si alguna línea calza.
-- `es_principal`: el rubro de nivel 2 con más líneas (desempate alfabético).
with lineas as (
    select distinct codigo_externo, correlativo, rubro1, rubro2
    from {{ ref('stg_bulk__oferta') }}
    where rubro1 is not null and rubro2 is not null
),

conteo as (
    select codigo_externo, rubro1, rubro2, count(*) as n_lineas
    from lineas
    group by 1, 2, 3
)

select
    *,
    row_number() over (partition by codigo_externo order by n_lineas desc, rubro2, rubro1) = 1 as es_principal
from conteo
