{{ config(indexes=[{'columns': ['codigo_externo'], 'unique': True}]) }}

-- Competencia efectiva por licitación, desde las ofertas:
--   competencia_descalificada: hubo 2 o más oferentes y todos menos el ganador fueron rechazados.
--   razon_sobre_mas_barata: cuánto del monto adjudicado se pagó por sobre la oferta aceptada más
--     barata de cada línea (solo líneas con 2+ aceptadas en la misma moneda; se ignoran ofertas
--     "baratas" bajo 30 % de la ganadora, que suelen ser errores como $1).
with oferente as (
    select codigo_externo, codigo_proveedor,
           bool_or(es_seleccionada) as gano,
           bool_or(estado_oferta = 'Aceptada') as aceptada
    from {{ ref('stg_bulk__oferta') }}
    where codigo_proveedor is not null
    group by 1, 2
),

por_licitacion as (
    select codigo_externo,
           count(*) as n_oferentes,
           count(*) filter (where aceptada) as n_aceptados,
           count(*) filter (where not aceptada) as n_rechazados,
           bool_or(gano and aceptada) as ganador_aceptado
    from oferente
    group by 1
),

linea as (
    select codigo_externo, correlativo,
           max(monto_unitario_oferta) filter (where es_seleccionada) as pu_ganador,
           min(monto_unitario_oferta) filter (where estado_oferta = 'Aceptada' and monto_unitario_oferta > 0) as pu_minimo,
           count(distinct codigo_proveedor) filter (where estado_oferta = 'Aceptada') as n_aceptadas,
           count(distinct moneda_oferta) as n_monedas,
           max(cantidad_adjudicada) filter (where es_seleccionada) as cantidad
    from {{ ref('stg_bulk__oferta') }}
    group by 1, 2
    having count(*) filter (where es_seleccionada) = 1
),

sobreprecio as (
    select codigo_externo,
           sum(pu_ganador * cantidad) as base,
           sum(greatest(pu_ganador - pu_minimo, 0) * cantidad) as extra
    from linea
    where n_aceptadas >= 2 and n_monedas = 1 and pu_minimo >= 0.3 * pu_ganador and cantidad > 0
    group by 1
)

select
    p.codigo_externo,
    p.n_oferentes,
    p.n_aceptados,
    p.n_rechazados,
    p.n_oferentes >= 2 and p.n_aceptados = 1 and p.n_rechazados >= 1 and p.ganador_aceptado
        as competencia_descalificada,
    case when s.base > 0 then s.extra / s.base end as razon_sobre_mas_barata
from por_licitacion p
left join sobreprecio s using (codigo_externo)
