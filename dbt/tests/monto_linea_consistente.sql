-- En las ofertas seleccionadas, monto de la línea = unitario × cantidad adjudicada
-- (tolerancia relativa: los montos grandes vienen en notación científica).
select codigo_externo, row_num, monto_unitario_oferta, cantidad_adjudicada, monto_linea_adjudicada
from {{ ref('stg_bulk__oferta') }}
where es_seleccionada
  and abs(monto_linea_adjudicada - monto_unitario_oferta * cantidad_adjudicada)
      > greatest(1, 1e-6 * abs(monto_linea_adjudicada))
