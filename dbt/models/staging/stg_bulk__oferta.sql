{{ config(
    materialized='incremental',
    incremental_strategy='delete+insert',
    unique_key='source_month',
    indexes=[{'columns': ['codigo_externo']}, {'columns': ['source_month']}, {'columns': ['codigo_proveedor']}],
) }}

-- Una fila por línea del CSV masivo: oferta de un proveedor a un ítem de una licitación.
-- Se reconstruye la fila (cabecera de la licitación || diferencias de la fila) con
-- LATERAL ... OFFSET 0: obliga a calcular la fusión de jsonb una vez por fila. Sin eso
-- PostgreSQL la recalcula por cada columna extraída (~30 veces); un CTE `materialized`
-- también lo evita, pero vuelca todas las filas a temporales (~16 GB con 33 meses).
with filas as (
    select f.source_month, f.row_num, f.codigo_externo, m.data, l.extracted_at
    from {{ source('raw', 'bulk_fila') }} f
    join {{ source('raw', 'bulk_licitacion') }} l using (source_month, codigo_externo)
    cross join lateral (select l.data || f.data as data offset 0) m
    -- Si un código aparece en más de un mes, solo el de la extracción más reciente
    -- (la misma regla que stg_bulk__licitacion).
    where not exists (
        select 1 from {{ source('raw', 'bulk_licitacion') }} l2
        where l2.codigo_externo = l.codigo_externo
          and (l2.extracted_at, l2.source_month) > (l.extracted_at, l.source_month)
    )
    {% if is_incremental() %}
    -- Solo los meses recargados desde la última corrida (backfill reemplaza meses completos).
    and f.source_month in (
        select source_month from {{ source('raw', 'bulk_licitacion') }}
        group by source_month
        having max(extracted_at) > (select coalesce(max(extracted_at), '-infinity') from {{ this }})
    )
    {% endif %}
),

tipada as (
    select
        source_month,
        row_num,
        codigo_externo,
        {{ to_num("data ->> 'Correlativo'") }}::int as correlativo,
        data ->> 'Codigoitem' as codigo_item,
        data ->> 'CodigoProductoONU' as codigo_producto_onu,
        data ->> 'Rubro1' as rubro1,
        data ->> 'Rubro2' as rubro2,
        data ->> 'Rubro3' as rubro3,
        {{ col('data', ['Nombre producto genrico', 'Nombre producto genérico']) }} as nombre_producto,
        {{ col('data', ['Nombre linea Adquisicion', 'Nombre línea Adquisición']) }} as nombre_linea,
        {{ col('data', ['Descripcion linea Adquisicion', 'Descripción línea Adquisición']) }} as descripcion_linea,
        data ->> 'UnidadMedida' as unidad_medida,
        {{ to_num("data ->> 'Cantidad'") }} as cantidad_solicitada,
        data ->> 'CodigoProveedor' as codigo_proveedor,
        data ->> 'CodigoSucursalProveedor' as codigo_sucursal_proveedor,
        data ->> 'RutProveedor' as rut_proveedor,
        data ->> 'NombreProveedor' as nombre_proveedor,
        data ->> 'RazonSocialProveedor' as razon_social_proveedor,
        data ->> 'Nombre de la Oferta' as nombre_oferta,
        data ->> 'Estado Oferta' as estado_oferta,
        data ->> 'Moneda de la Oferta' as moneda_oferta_nombre,
        {{ to_num("data ->> 'MontoUnitarioOferta'") }} as monto_unitario_oferta,
        {{ to_num("data ->> 'Cantidad Ofertada'") }} as cantidad_ofertada,
        {{ to_num("data ->> 'Valor Total Ofertado'") }} as valor_total_ofertado,
        {{ to_num("data ->> 'CantidadAdjudicada'") }} as cantidad_adjudicada,
        {{ to_num("data ->> 'MontoLineaAdjudica'") }} as monto_linea_adjudicada,
        {{ to_fecha("data ->> 'FechaEnvioOferta'") }} as fecha_envio_oferta,
        -- 'Perdedora' aparece en 2007 como sinónimo de no seleccionada.
        data ->> 'Oferta seleccionada' = 'Seleccionada' as es_seleccionada,
        extracted_at
    from filas
)

select
    t.*,
    -- Subconsulta escalar y no join: con un join el planificador estimaba mal las filas,
    -- elegía un merge join y ordenaba cada fila con su jsonb (~16 GB de temporales).
    (select m.codigo from {{ ref('moneda') }} m where m.nombre = t.moneda_oferta_nombre) as moneda_oferta,
    -- Cantidad adjudicada >100× lo ofertado y lo solicitado: casi siempre un monto escrito
    -- en el campo cantidad (p. ej. 287.165.982 unidades de un ítem solicitado 1 vez), que
    -- infla monto_linea_adjudicada a ~10^16 CLP. Ver docs/fase2_modelado.md.
    es_seleccionada
        and cantidad_adjudicada > 100 * greatest(coalesce(cantidad_ofertada, 0), coalesce(cantidad_solicitada, 0))
        as cantidad_adjudicada_atipica
from tipada t
