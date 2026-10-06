-- Una fila por licitación desde la descarga masiva, tipada.
-- Si un código aparece en más de un mes, gana la extracción más reciente.
with fuente as (
    select
        *,
        row_number() over (partition by codigo_externo order by extracted_at desc, source_month desc) as rn
    from {{ source('raw', 'bulk_licitacion') }}
)

select
    codigo_externo,
    data ->> 'Codigo' as codigo,
    data ->> 'Nombre' as nombre,
    data ->> 'Descripcion' as descripcion,
    data ->> 'Tipo' as tipo,
    {{ col('data', ['Tipo de Adquisicion', 'Tipo de Adquisición']) }} as tipo_adquisicion,
    (data ->> 'CodigoEstado')::int as codigo_estado,
    data ->> 'Estado' as estado,
    data ->> 'CodigoOrganismo' as codigo_organismo,
    data ->> 'NombreOrganismo' as nombre_organismo,
    data ->> 'sector' as sector,
    data ->> 'RutUnidad' as rut_unidad,
    data ->> 'CodigoUnidad' as codigo_unidad,
    data ->> 'NombreUnidad' as nombre_unidad,
    data ->> 'ComunaUnidad' as comuna_unidad,
    data ->> 'RegionUnidad' as region_unidad,
    data ->> 'CodigoMoneda' as moneda,
    -- 0 en épocas antiguas significa "no informado".
    nullif({{ to_num("data ->> 'MontoEstimado'") }}, 0) as monto_estimado,
    data ->> 'VisibilidadMonto' = '1' as monto_estimado_visible,
    (data ->> 'Estimacion')::int as tipo_estimacion,
    {{ to_num("data ->> 'Monto Estimado Adjudicado'") }} as monto_estimado_adjudicado,
    {{ to_num("data ->> 'NumeroOferentes'") }}::int as numero_oferentes,
    {{ to_num("data ->> 'CantidadReclamos'") }}::int as cantidad_reclamos,
    data ->> 'FuenteFinanciamiento' as fuente_financiamiento,
    data ->> 'Modalidad' as modalidad_pago,
    data ->> 'Contrato' = '1' as requiere_contrato,
    data ->> 'Obras' = '1' as es_obra,
    data ->> 'TomaRazon' = '1' as requiere_toma_razon,
    {{ to_fecha("data ->> 'FechaCreacion'") }} as fecha_creacion,
    {{ to_fecha("data ->> 'FechaPublicacion'") }} as fecha_publicacion,
    {{ to_fecha("data ->> 'FechaCierre'") }} as fecha_cierre,
    -- En licitaciones no adjudicadas es la fecha estimada (Fase 0): ver fecha_adjudicacion en marts.
    {{ to_fecha("data ->> 'FechaAdjudicacion'") }} as fecha_adjudicacion_bruta,
    {{ to_fecha("data ->> 'FechaEstimadaAdjudicacion'") }} as fecha_estimada_adjudicacion,
    data ->> 'Link' as link,
    source_month,
    extracted_at
from fuente
where rn = 1
