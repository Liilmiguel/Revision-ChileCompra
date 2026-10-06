{{ config(indexes=[{'columns': ['codigo_externo'], 'unique': True}]) }}

-- Señales de riesgo por licitación adjudicada y su puntaje (0–100). Pesos en dbt_project.yml
-- (var senales); definiciones en docs/fase3_preguntas.md. Una señal no prueba irregularidad.
with lic as (
    select l.codigo_externo, l.tipo, l.fecha_cierre - l.fecha_publicacion as dias_oferta,
           e.estado_grupo, o.n_proveedores_oferentes, o.moneda_adjudicada,
           case when o.moneda_adjudicada = l.moneda and l.monto_estimado > 0
                then o.monto_adjudicado / l.monto_estimado end as razon
    from {{ ref('int_licitacion') }} l
    left join {{ ref('estado_licitacion') }} e on e.codigo_estado = l.codigo_estado_actual
    left join {{ ref('int_licitacion__ofertas') }} o using (codigo_externo)
),

p10 as (
    select tipo, percentile_cont(0.10) within group (order by dias_oferta) as p10
    from lic where dias_oferta >= 0 group by 1
),

precio_ref as (
    select distinct o.codigo_externo
    from {{ ref('stg_bulk__oferta') }} o
    join {{ ref('int_precio_referencia') }} r
      on r.onu = o.codigo_producto_onu and r.um = lower(trim(o.unidad_medida))
    where o.es_seleccionada and o.moneda_oferta = 'CLP' and o.monto_unitario_oferta > 5 * r.mediana
),

s as (
    select
        lic.codigo_externo,
        coalesce(lic.n_proveedores_oferentes = 1, false) as s_oferente_unico,
        coalesce(c.competencia_descalificada, false) as s_competencia_descalificada,
        coalesce(c.razon_sobre_mas_barata > 1.0 / 3, false) as s_sobre_oferta_barata,
        -- razón bajo 10 %: suministro por precio unitario, no comparable con el estimado.
        coalesce(lic.razon > 1.2, false) as s_sobre_estimado,
        coalesce(lic.dias_oferta < p10.p10, false) as s_plazo_corto,
        pr.codigo_externo is not null as s_precio_referencia,
        c.razon_sobre_mas_barata
    from lic
    left join {{ ref('int_licitacion_competencia') }} c using (codigo_externo)
    left join p10 using (tipo)
    left join precio_ref pr using (codigo_externo)
    where lic.estado_grupo = 'Adjudicada'
)

{% set w = var('senales') %}
select
    *,
    {{ w.oferente_unico }} * s_oferente_unico::int
    + {{ w.competencia_descalificada }} * s_competencia_descalificada::int
    + {{ w.sobre_oferta_barata }} * s_sobre_oferta_barata::int
    + {{ w.sobre_estimado }} * s_sobre_estimado::int
    + {{ w.plazo_corto }} * s_plazo_corto::int
    + {{ w.precio_referencia }} * s_precio_referencia::int as puntaje_riesgo
from s
