{{ config(indexes=[{'columns': ['codigo_externo'], 'unique': True}]) }}

-- Señales complementarias: no suman al puntaje de riesgo (que se mantiene comparable con
-- el análisis de la Fase 3), se muestran como marcas aparte. Ver docs/fase3_preguntas.md.
--
-- x_ofertas_identicas: dos o más proveedores ofertan exactamente el mismo total en pesos,
--   desde $100.000 y no múltiplo de $1.000. Con montos redondos las coincidencias son
--   frecuentes (13.449 licitaciones sin esa condición, 3.255 con ella); con un total como
--   $14.813.305 repetido es difícil que sea azar. También ocurre con precios regulados o
--   aranceles fijos: es una pista, no una prueba.
-- x_fraccionamiento: licitación L1 / E2 (< 100 UTM) adjudicada a un proveedor que en ±30
--   días ganó otras 2+ del mismo organismo y rubro, sumando más de 100 UTM entre todas.
--   Es la forma de eludir una licitación mayor dividiendo la compra.
--
-- Descartada: "estimado justo bajo el tope del tipo". Los estimados se acumulan en montos
-- redondos ($5 y $6 millones en L1), no pegados al tope: entre 95 % y 100 % del tope hay
-- menos L1 que entre 90 % y 95 %.
with lic as (
    select codigo_externo, fecha_publicacion, tipo, codigo_organismo
    from {{ ref('int_licitacion') }}
),

totales as (
    select codigo_externo, codigo_proveedor, sum(valor_total_ofertado) as total
    from {{ ref('stg_bulk__oferta') }}
    where codigo_proveedor is not null and moneda_oferta = 'CLP'
    group by 1, 2
),

identicas as (
    select distinct codigo_externo
    from totales
    where total >= 100000 and mod(total, 1000) <> 0
    group by codigo_externo, total
    having count(*) >= 2
),

adjudicaciones as (
    select codigo_externo, codigo_proveedor, sum(monto_linea_adjudicada) as monto_adjudicado
    from {{ ref('int_linea_adjudicada') }}
    where motivo_atipico is null and codigo_proveedor is not null and moneda_oferta = 'CLP'
    group by 1, 2
),

-- Adjudicaciones menores (< 100 UTM en pesos) con su rubro principal.
menores as (
    select a.codigo_externo, a.codigo_proveedor, t.codigo_organismo, t.fecha_publicacion,
        r.rubro2, a.monto_adjudicado
    from adjudicaciones a
    join lic t using (codigo_externo)
    join {{ ref('int_licitacion_rubro') }} r on r.codigo_externo = a.codigo_externo and r.es_principal
    where t.tipo in ('L1', 'E2')
        and a.monto_adjudicado < 100 * {{ var('utm_clp') }}
),

ventana as (
    select m.codigo_externo, count(distinct o.codigo_externo) as n, sum(o.monto_adjudicado) as suma
    from menores m
    join menores o
        on o.codigo_proveedor = m.codigo_proveedor
        and o.codigo_organismo = m.codigo_organismo
        and o.rubro2 = m.rubro2
        and o.fecha_publicacion between m.fecha_publicacion - 30 and m.fecha_publicacion + 30
    group by m.codigo_externo
)

select
    t.codigo_externo,
    i.codigo_externo is not null as x_ofertas_identicas,
    coalesce(v.n >= 3 and v.suma > 100 * {{ var('utm_clp') }}, false) as x_fraccionamiento,
    v.n as fraccionamiento_n,
    v.suma as fraccionamiento_monto
from lic t
left join identicas i using (codigo_externo)
left join ventana v using (codigo_externo)
