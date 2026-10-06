-- Agregados de ofertas y adjudicación por licitación.
select
    codigo_externo,
    count(*) as n_filas_oferta,
    count(distinct correlativo) as n_lineas,
    count(distinct codigo_proveedor) as n_proveedores_oferentes,
    count(distinct codigo_proveedor) filter (where es_seleccionada) as n_proveedores_adjudicados,
    count(*) filter (where es_seleccionada) as n_lineas_adjudicadas,
    -- Sin las líneas con cantidad adjudicada atípica; el bruto queda para comparar.
    sum(monto_linea_adjudicada) filter (where es_seleccionada and not cantidad_adjudicada_atipica) as monto_adjudicado,
    sum(monto_linea_adjudicada) filter (where es_seleccionada) as monto_adjudicado_bruto,
    count(*) filter (where cantidad_adjudicada_atipica) as n_lineas_atipicas,
    -- Los montos están en la moneda de cada oferta: solo se suman si es una sola.
    case
        when count(distinct moneda_oferta) filter (where es_seleccionada) = 1
            then min(moneda_oferta) filter (where es_seleccionada)
        when count(*) filter (where es_seleccionada) > 0 then 'MIXTA'
    end as moneda_adjudicada
from {{ ref('stg_bulk__oferta') }}
group by codigo_externo
