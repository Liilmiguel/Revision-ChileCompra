-- Agregados de ofertas y adjudicación por licitación.
select
    o.codigo_externo,
    count(*) as n_filas_oferta,
    count(distinct o.correlativo) as n_lineas,
    count(distinct o.codigo_proveedor) as n_proveedores_oferentes,
    count(distinct o.codigo_proveedor) filter (where o.es_seleccionada) as n_proveedores_adjudicados,
    count(*) filter (where o.es_seleccionada) as n_lineas_adjudicadas,
    -- Sin las líneas con monto atípico (int_linea_adjudicada); el bruto queda para comparar.
    sum(o.monto_linea_adjudicada) filter (where o.es_seleccionada and a.motivo_atipico is null) as monto_adjudicado,
    sum(o.monto_linea_adjudicada) filter (where o.es_seleccionada) as monto_adjudicado_bruto,
    count(a.motivo_atipico) as n_lineas_atipicas,
    -- Los montos están en la moneda de cada oferta: solo se suman si es una sola.
    case
        when count(distinct o.moneda_oferta) filter (where o.es_seleccionada) = 1
            then min(o.moneda_oferta) filter (where o.es_seleccionada)
        when count(*) filter (where o.es_seleccionada) > 0 then 'MIXTA'
    end as moneda_adjudicada
from {{ ref('stg_bulk__oferta') }} o
left join {{ ref('int_linea_adjudicada') }} a using (source_month, row_num)
group by o.codigo_externo
