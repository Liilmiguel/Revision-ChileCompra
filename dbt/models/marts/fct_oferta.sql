-- Vista: evita duplicar las filas de stg_bulk__oferta (la tabla grande del proyecto).
{{ config(materialized='view') }}

-- Una fila por oferta de un proveedor a una línea, con el contexto de la licitación.
select
    o.codigo_externo,
    o.row_num,
    o.source_month,
    o.correlativo,
    o.codigo_producto_onu,
    o.rubro1,
    o.nombre_producto,
    o.cantidad_solicitada,
    o.unidad_medida,
    o.codigo_proveedor,
    o.rut_proveedor,
    o.nombre_proveedor,
    o.estado_oferta,
    o.moneda_oferta,
    o.monto_unitario_oferta,
    o.cantidad_ofertada,
    o.valor_total_ofertado,
    o.es_seleccionada,
    o.cantidad_adjudicada,
    case when o.es_seleccionada and a.motivo_atipico is null then o.monto_linea_adjudicada end as monto_adjudicado,
    a.motivo_atipico,
    o.fecha_envio_oferta,
    l.codigo_organismo,
    l.fecha_publicacion,
    l.estado_grupo
from {{ ref('stg_bulk__oferta') }} o
join {{ ref('fct_licitacion') }} l using (codigo_externo)
left join {{ ref('int_linea_adjudicada') }} a on a.source_month = o.source_month and a.row_num = o.row_num
