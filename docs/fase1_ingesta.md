# Fase 1: ingesta a raw

Estado al 2026-10-05.

## Decisiones

- **Fuente principal: descarga masiva mensual.** Trae ofertas y montos que la API no
  expone (Fase 0). Un request por mes, sin ticket. Se refresca cuando cambia el
  `Last-Modified` del zip: ChileCompra regenera meses recientes (2026-8 y 2026-9 tenían
  fecha 2026-10-04/05).
- **API solo para el incremental**: listado por día de evento + detalle de cada código.
  Pausa de 1,5 s entre llamadas → un día hábil (~500 licitaciones) toma ~13 minutos.
- **Raw sin tipar**: todo como texto en jsonb; el tipado (montos en tres formatos,
  fechas, renombre de columnas entre épocas) es trabajo de staging (Fase 2, dbt).
- Se descartó `backfill.py` por API con cupo diario del plan original: la masiva cubre
  el histórico.

## Hallazgos nuevos

- **Codificación mixta**: el CSV es mayormente cp1252 pero trae campos en UTF-8
  (`P\xc3\x81` = "PÁ") y bytes que cp1252 no define (0x81). Leerlo como cp1252 falla en
  2026-9. Se decodifica campo a campo (UTF-8 si es válido, si no cp1252). Verificado: 0
  nombres con mojibake (`Ã`, `Â`) en 4 meses cargados.
- **Las columnas cambian entre épocas**: 2007-1 tiene 106 columnas con tildes
  (`Nombre producto genérico`, `Tipo de Adquisición`, `Estado final Oferta`,
  `UnidadMedida.1`); 2024–2026 tienen 110, sin tildes (`Nombre producto genrico`) y con
  `ValorTiempoRenovacion`. Staging necesita un mapeo de nombres.
- **Volumen**: guardando cada fila completa, 1,26 M filas ocupaban 3,2 GB (2,5 KB/fila;
  lz4 fue peor que pglz). ~85 de ~110 columnas son constantes por licitación, así que
  se guardan una vez (`raw.bulk_licitacion`) y las filas solo con lo que difiere: 1,1 GB,
  3× menos, con reconstrucción exacta verificada (0 diferencias en 77.821 filas de 2026-9).

| mes | filas CSV | licitaciones |
|---|---|---|
| 2007-1 | 827.812 | 35.087 |
| 2024-1 | 206.454 | 11.712 |
| 2026-8 | 145.086 | 8.142 |
| 2026-9 | 77.821 | 4.501 (mes aún abierto) |

[Suponiendo] Con ~850 bytes por fila, el histórico 2007–2026 completo pesaría del
orden de decenas de GB. Conviene partir el backfill desde el año que exijan las
preguntas, no desde 2007.

## Pendiente

- Semántica exacta del filtro `fecha` del listado y cuota diaria de la API.
- Un día del incremental que falla queda en la bitácora como error y no se reintenta
  solo: hay que correr `observatorio incremental --from <día>`.
