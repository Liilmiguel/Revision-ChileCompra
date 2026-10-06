-- Pares de proveedores que ofertan juntos en licitaciones chicas (2–4 oferentes): cuántas veces
-- coincidieron y quién ganó. El patrón "acompañante" (5+ coincidencias, el ganador gana 80 %+,
-- el otro nunca gana) es una señal clásica de competencia simulada, pero también aparece en
-- mercados de nicho con pocos actores.
with bid as (
    select codigo_externo, codigo_proveedor, bool_or(es_seleccionada) as gano
    from {{ ref('stg_bulk__oferta') }}
    where codigo_proveedor is not null
    group by 1, 2
),

chicas as (
    select codigo_externo from bid group by 1 having count(*) between 2 and 4
),

pares as (
    select a.codigo_proveedor as ganador, b.codigo_proveedor as acompanante,
           count(*) as juntos,
           count(*) filter (where a.gano and not b.gano) as gana_ganador,
           count(*) filter (where b.gano) as gana_acompanante
    from bid a
    join bid b on a.codigo_externo = b.codigo_externo and a.codigo_proveedor <> b.codigo_proveedor
    join chicas c on c.codigo_externo = a.codigo_externo
    group by 1, 2
    having count(*) >= 5
)

select *,
       gana_acompanante = 0 and gana_ganador >= 0.8 * juntos as es_acompanante
from pares
where gana_ganador >= 0.8 * juntos and gana_acompanante = 0
