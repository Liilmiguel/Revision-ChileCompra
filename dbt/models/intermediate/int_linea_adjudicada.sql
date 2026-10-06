{{ config(indexes=[{'columns': ['codigo_externo']}, {'columns': ['codigo_proveedor']}]) }}

-- Líneas adjudicadas con la marca de monto atípico (error de captura). Tres reglas,
-- verificadas a mano sobre 2024-01..2026-09 (docs/fase3_preguntas.md):
--   cantidad: cantidad adjudicada >100× lo ofertado y lo solicitado.
--   tope:     la línea vale >10× el tope legal del tipo de licitación (L1 < 100 UTM, ...).
--             Ej.: una L1 adjudicada en $5,25 billones (estimado de 3 millones escrito
--             como cantidad ofertada). 39 líneas sumaban ~24 % del monto del periodo.
--   estimado: la línea vale >10× un estimado creíble (≥ $1 millón) en la misma moneda.
with tope (tipo, utm) as (
    values ('L1', 100), ('E2', 100), ('LE', 1000), ('CO', 1000),
           ('LP', 2000), ('B2', 2000), ('LQ', 5000), ('H2', 5000)
),

lineas as (
    select
        o.codigo_externo, o.source_month, o.row_num, o.correlativo, o.codigo_proveedor, o.moneda_oferta,
        o.monto_linea_adjudicada, o.cantidad_adjudicada_atipica,
        l.tipo, l.moneda as moneda_licitacion, l.monto_estimado,
        t.utm::numeric * {{ var('utm_clp') }} as tope_clp
    from {{ ref('stg_bulk__oferta') }} o
    join {{ ref('stg_bulk__licitacion') }} l using (codigo_externo)
    left join tope t on t.tipo = l.tipo
    where o.es_seleccionada
)

select
    *,
    case
        when cantidad_adjudicada_atipica then 'cantidad'
        when moneda_oferta = 'CLP' and monto_linea_adjudicada > 10 * tope_clp then 'tope'
        when moneda_oferta = moneda_licitacion and monto_estimado >= 1000000
             and monto_linea_adjudicada > 10 * monto_estimado then 'estimado'
    end as motivo_atipico
from lineas
