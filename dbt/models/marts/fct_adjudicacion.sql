{{ config(indexes=[{'columns': ['codigo_externo']}, {'columns': ['codigo_proveedor']}]) }}

-- Una fila por licitación × proveedor adjudicado: base para medir concentración.
-- Excluye líneas con monto atípico (int_linea_adjudicada).
select
    codigo_externo,
    codigo_proveedor,
    moneda_oferta as moneda,
    count(*) as n_lineas,
    sum(monto_linea_adjudicada) as monto_adjudicado
from {{ ref('int_linea_adjudicada') }}
where motivo_atipico is null and codigo_proveedor is not null
group by codigo_externo, codigo_proveedor, moneda_oferta
