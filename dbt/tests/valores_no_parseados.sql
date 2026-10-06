-- Avisa con cualquier valor y falla sobre 50: el archivo de 2026-3 trae bytes dañados en
-- origen (`Peso nhileno`, `8210a`) que quedan nulos en staging. Ver docs/fase2_modelado.md.
{{ config(warn_if='>0', error_if='>50') }}

-- Montos, cantidades y fechas que vienen informados en raw pero no se pudieron tipar.
with lic as (
    select key, value
    from {{ source('raw', 'bulk_licitacion') }}, jsonb_each_text(data)
    where value is not null
      and key in ('MontoEstimado', 'Monto Estimado Adjudicado', 'NumeroOferentes', 'CantidadReclamos')
),
fila as (
    select key, value
    from {{ source('raw', 'bulk_fila_completa') }}, jsonb_each_text(data)
    where value is not null
      and key in ('Cantidad', 'MontoUnitarioOferta', 'Valor Total Ofertado', 'Cantidad Ofertada',
                  'CantidadAdjudicada', 'MontoLineaAdjudica', 'Correlativo')
),
fechas as (
    select key, value
    from {{ source('raw', 'bulk_licitacion') }}, jsonb_each_text(data)
    where value is not null and key in ('FechaPublicacion', 'FechaCierre', 'FechaAdjudicacion', 'FechaCreacion')
)
select key, value from lic where {{ to_num('value') }} is null
union all
select key, value from fila where {{ to_num('value') }} is null
union all
select key, value from fechas where value !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}'
