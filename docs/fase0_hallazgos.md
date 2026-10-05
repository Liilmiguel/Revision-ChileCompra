# Fase 0: hallazgos

Estado al 2026-10-05. Solo estadísticas agregadas; las muestras crudas quedan en
`data/samples/` (ignorado por git).

## Pendiente

- **API (`licitaciones.json`) sin explorar**: no hay `MERCADO_PUBLICO_TICKET` en el
  entorno. Con un ticket inválido la API responde HTTP 203 con
  `{"Codigo":203,"Mensaje":"Ticket no válido."}`, no un 4xx: `api_client.py` debe
  validar `Codigo` en el cuerpo, no solo el status HTTP.
- Comparar API vs. masiva para los mismos `CodigoExterno` (montos, estados, fechas).

## Descarga masiva (`lic-da/2026-8.zip`)

Comando: `uv run python scripts/phase0_explore.py --bulk-month 2026-8`

| aspecto | hallazgo |
|---|---|
| tamaño | 17 MB zip → 288 MB CSV, un solo archivo `lic_2026-8.csv` |
| formato | separador `;`, campos entre comillas, nulos como `NA` |
| codificación | **cp1252**, no latin-1 (aparecen comillas tipográficas `\x93`/`\x94`). El perfilador ya usa cp1252 |
| fin de línea | CR solo (no CRLF); hay CR embebidos en `Descripcion`, `DescripcionProveedor`, `Descripcion linea Adquisicion`, etc. Leer siempre con un parser CSV con `newline=""`, nunca por líneas |
| cabecera | `Nombre producto genrico` (la é se perdió en origen) y una columna duplicada `DescripcionCriteriosRequisitosSociales.1`. Hay que renombrar por posición/mapeo explícito |
| granularidad | **145.086 filas para 8.142 licitaciones**: una fila por licitación × ítem × oferta. No es una tabla de licitaciones |
| partición | el mes del archivo es el de `FechaPublicacion` (100 % en 2026-08); `FechaCreacion` se reparte en meses anteriores |
| consistencia | `CodigoExterno` → un único `Codigo` y un único `CodigoEstado` en todo el archivo |
| foto | archivo generado el 2026-10-04: los estados son a esa fecha. Meses recientes deben re-descargarse para capturar adjudicaciones posteriores |

### Estados (filas)

Cerrada (6) 71.622 · Adjudicada (8) 67.681 · Desierta (7) 3.373 · Revocada (15) 2.274 · Suspendida 136.

### Montos: el hallazgo más importante

`MontoEstimado` viene en **notación científica con coma decimal en el 41 % de las
filas** (`1,4e+07`), con solo 1–3 dígitos significativos. Ese valor está redondeado
en origen y **no sirve para análisis de sobrecosto ni comparación estimado vs.
adjudicado**. Opciones: tomar `MontoEstimado` desde la API (por confirmar que venga
completo) o tratarlo como orden de magnitud.

| columna | entero | coma decimal | científica | NA |
|---|---|---|---|---|
| `MontoEstimado` | 85.127 | 262 | 59.682 | 15 |
| `Monto Estimado Adjudicado` | 92.464 | 0 | 3.610 | 49.012 |
| `MontoLineaAdjudica` | 144.435 | 102 | 549 | 0 |
| `MontoUnitarioOferta` | 140.138 | 2.242 | 2.706 | 0 |
| `Valor Total Ofertado` | 139.142 | 1.193 | 4.751 | 0 |

El parser de staging debe aceptar los tres formatos (`int`, `1234,5`, `1,4e+07`) y
marcar con un flag los valores que venían en científica.

### Otras trampas

- `FechaAdjudicacion` viene poblada también en licitaciones no adjudicadas (es la
  fecha estimada): no sirve como indicador de adjudicación; usar `CodigoEstado = 8`
  y `Oferta seleccionada = 'Seleccionada'`.
- 35 de 16.954 líneas adjudicadas tienen más de una oferta seleccionada
  (adjudicación múltiple, legítima).
- 139 combinaciones (`CodigoExterno`, `Correlativo`, `CodigoProveedor`,
  `Nombre de la Oferta`) se repiten: la clave natural de oferta necesita más campos
  (probablemente `FechaEnvioOferta` o el monto). Resolver en Fase 1.
- `TipoDuracionContrato` y `PeriodoTiempoRenovacion` vienen 100 % vacías.

## Decisión propuesta

La masiva es viable para el backfill histórico (`bulk.py`): un request por mes,
sin ticket ni cupo. La API queda para el incremental diario y para completar
`MontoEstimado`, sujeto a validar con ticket.
