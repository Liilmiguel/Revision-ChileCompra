-- Estado y montos del detalle de la API (más reciente que la masiva para meses abiertos).
select
    codigo_externo,
    (data ->> 'CodigoEstado')::int as codigo_estado,
    data ->> 'Estado' as estado,
    (data ->> 'MontoEstimado')::numeric as monto_estimado,
    (data ->> 'VisibilidadMonto')::int = 1 as monto_estimado_visible,
    (data -> 'Adjudicacion' ->> 'NumeroOferentes')::int as numero_oferentes,
    left(data -> 'Fechas' ->> 'FechaAdjudicacion', 10)::date as fecha_adjudicacion_bruta,
    extracted_at
from {{ source('raw', 'api_licitacion') }}
