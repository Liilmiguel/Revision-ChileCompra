-- Avisa con cualquier valor y falla sobre 50: el archivo de 2026-3 trae bytes dañados en
-- origen (`Peso nhileno`, `8210a`) que quedan nulos en staging. Ver docs/fase2_modelado.md.
{{ config(warn_if='>0', error_if='>50') }}

-- Toda moneda de oferta informada debe estar en el seed `moneda`.
select distinct f.data ->> 'Moneda de la Oferta' as moneda
from {{ source('raw', 'bulk_fila_completa') }} f
left join {{ ref('moneda') }} m on m.nombre = f.data ->> 'Moneda de la Oferta'
where f.data ->> 'Moneda de la Oferta' is not null and m.codigo is null
