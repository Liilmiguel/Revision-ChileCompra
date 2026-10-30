{{ config(indexes=[{'columns': ['codigo_externo'], 'unique': True}, {'columns': ['codigo_organismo']}]) }}

-- Una fila por licitación: identidad, comprador, estado actual, montos y competencia.
select
    l.codigo_externo,
    l.nombre,
    l.tipo,
    coalesce(t.descripcion, 'Otro') as tipo_descripcion,
    coalesce(t.orden, 99) as tipo_orden,
    l.tipo_adquisicion,
    l.codigo_organismo,
    l.nombre_organismo,
    l.sector,
    l.region_unidad,
    l.comuna_unidad,
    l.codigo_estado_actual as codigo_estado,
    e.estado_grupo,
    e.es_final as estado_es_final,
    l.fuente_estado,
    l.fecha_publicacion,
    date_trunc('month', l.fecha_publicacion)::date as mes_publicacion,
    l.fecha_cierre,
    l.fecha_cierre - l.fecha_publicacion as dias_publicacion_cierre,
    -- FechaAdjudicacion solo es real si la licitación está adjudicada (Fase 0).
    case when e.estado_grupo = 'Adjudicada' then l.fecha_adjudicacion_bruta_actual end as fecha_adjudicacion,
    case
        when e.estado_grupo = 'Adjudicada' then l.fecha_adjudicacion_bruta_actual - l.fecha_cierre
    end as dias_cierre_adjudicacion,
    l.moneda,
    l.monto_estimado,
    l.monto_estimado_visible,
    o.monto_adjudicado,
    o.monto_adjudicado_bruto,
    o.moneda_adjudicada,
    coalesce(o.n_lineas_atipicas, 0) as n_lineas_atipicas,
    case
        when o.moneda_adjudicada = l.moneda and l.monto_estimado > 0
            then o.monto_adjudicado / l.monto_estimado
    end as razon_adjudicado_estimado,
    l.numero_oferentes,
    coalesce(o.n_proveedores_oferentes, 0) as n_proveedores_oferentes,
    coalesce(o.n_proveedores_adjudicados, 0) as n_proveedores_adjudicados,
    coalesce(o.n_lineas, 0) as n_lineas,
    coalesce(o.n_lineas_adjudicadas, 0) as n_lineas_adjudicadas,
    o.n_proveedores_oferentes = 1 as es_oferente_unico,
    coalesce(s.puntaje_riesgo, 0) as puntaje_riesgo,
    coalesce(s.s_oferente_unico, false) as s_oferente_unico,
    coalesce(s.s_competencia_descalificada, false) as s_competencia_descalificada,
    coalesce(s.s_sobre_oferta_barata, false) as s_sobre_oferta_barata,
    coalesce(s.s_sobre_estimado, false) as s_sobre_estimado,
    coalesce(s.s_plazo_corto, false) as s_plazo_corto,
    coalesce(s.s_precio_referencia, false) as s_precio_referencia,
    s.razon_sobre_mas_barata,
    coalesce(x.x_ofertas_identicas, false) as x_ofertas_identicas,
    coalesce(x.x_fraccionamiento, false) as x_fraccionamiento,
    x.fraccionamiento_n,
    x.fraccionamiento_monto,
    r.rubro1 as rubro1_principal,
    r.rubro2 as rubro2_principal,
    l.cantidad_reclamos,
    l.es_obra,
    l.link,
    l.source_month
from {{ ref('int_licitacion') }} l
left join {{ ref('estado_licitacion') }} e on e.codigo_estado = l.codigo_estado_actual
left join {{ ref('tipo_licitacion') }} t on t.tipo = l.tipo
left join {{ ref('int_licitacion__ofertas') }} o using (codigo_externo)
left join {{ ref('int_licitacion_senales') }} s using (codigo_externo)
left join {{ ref('int_licitacion_senales_extra') }} x using (codigo_externo)
left join {{ ref('int_licitacion_rubro') }} r on r.codigo_externo = l.codigo_externo and r.es_principal
