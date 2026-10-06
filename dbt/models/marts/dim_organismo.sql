-- Una fila por organismo comprador, con el nombre más reciente.
with ultimo as (
    select distinct on (codigo_organismo) codigo_organismo, nombre_organismo, sector
    from {{ ref('fct_licitacion') }}
    order by codigo_organismo, fecha_publicacion desc nulls last
)

select
    u.*,
    count(*) as n_licitaciones,
    count(*) filter (where l.estado_grupo = 'Adjudicada') as n_adjudicadas,
    count(*) filter (where l.estado_grupo = 'Desierta') as n_desiertas,
    count(*) filter (where l.es_oferente_unico) as n_oferente_unico,
    sum(l.monto_adjudicado) filter (where l.moneda_adjudicada = 'CLP') as monto_adjudicado_clp
from ultimo u
join {{ ref('fct_licitacion') }} l using (codigo_organismo)
group by u.codigo_organismo, u.nombre_organismo, u.sector
