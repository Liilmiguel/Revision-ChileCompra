-- Precio de referencia por producto (código ONU × unidad) para bienes con precios homogéneos.
-- Los códigos ONU son categorías amplias, así que solo se usan productos con al menos 30
-- licitaciones y rango intercuartil estrecho (p75 / p25 < 2,5); servicios y unidades de tiempo
-- quedan fuera. Aun así una diferencia puede ser de presentación (caja vs unidad).
with sel as (
    select codigo_externo, codigo_producto_onu as onu, lower(trim(unidad_medida)) as um, monto_unitario_oferta as pu
    from {{ ref('stg_bulk__oferta') }}
    where es_seleccionada and moneda_oferta = 'CLP' and monto_unitario_oferta > 0
      and codigo_producto_onu !~ '^(7|8|9)'  -- segmentos ONU 70–95: servicios
      and lower(trim(unidad_medida)) not in (
          'global', 'servicio', 'servicios', 'mes', 'meses', 'hora', 'horas', 'dia', 'día', 'dias', 'días',
          'año', 'sesión', 'jornada'
      )
)

select onu, um,
       count(distinct codigo_externo) as n_licitaciones,
       percentile_cont(0.5) within group (order by pu) as mediana,
       percentile_cont(0.25) within group (order by pu) as p25,
       percentile_cont(0.75) within group (order by pu) as p75
from sel
group by 1, 2
having count(distinct codigo_externo) >= 30
   and percentile_cont(0.75) within group (order by pu) < 2.5 * percentile_cont(0.25) within group (order by pu)
