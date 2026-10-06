-- Una fila por proveedor (CodigoProveedor), con el nombre de su oferta más reciente.
with ultimo as (
    select distinct on (codigo_proveedor)
        codigo_proveedor, rut_proveedor, nombre_proveedor, razon_social_proveedor
    from {{ ref('stg_bulk__oferta') }}
    where codigo_proveedor is not null
    order by codigo_proveedor, source_month desc, row_num desc
)

select
    u.*,
    count(distinct o.codigo_externo) as n_licitaciones_ofertadas,
    count(distinct o.codigo_externo) filter (where o.es_seleccionada) as n_licitaciones_adjudicadas,
    sum(o.monto_adjudicado) filter (where o.moneda_oferta = 'CLP') as monto_adjudicado_clp
from ultimo u
join {{ ref('fct_oferta') }} o using (codigo_proveedor)
group by u.codigo_proveedor, u.rut_proveedor, u.nombre_proveedor, u.razon_social_proveedor
