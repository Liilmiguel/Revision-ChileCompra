-- Licitación con el estado más reciente: el de la API si su detalle es posterior a la
-- descarga masiva (los meses recientes cambian de estado después de publicado el zip).
select
    b.*,
    coalesce(case when a.extracted_at > b.extracted_at then a.codigo_estado end, b.codigo_estado) as codigo_estado_actual,
    case when a.extracted_at > b.extracted_at then 'api' else 'masiva' end as fuente_estado,
    coalesce(
        case when a.extracted_at > b.extracted_at then a.fecha_adjudicacion_bruta end,
        b.fecha_adjudicacion_bruta
    ) as fecha_adjudicacion_bruta_actual
from {{ ref('stg_bulk__licitacion') }} b
left join {{ ref('stg_api__licitacion') }} a using (codigo_externo)
