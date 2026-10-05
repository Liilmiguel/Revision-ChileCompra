# Fase 0: hallazgos

Estado al 2026-10-05. Solo estadísticas agregadas; las muestras crudas quedan en
`data/samples/` (ignorado por git).

## Pendiente

- Validar la semántica del filtro `fecha` del listado con más días (ver abajo).
- Cuota diaria real de la API con este ticket (no se observó rechazo en ~40 llamadas).

## API (`licitaciones.json`)

Comandos: `phase0_explore.py --dates 01082026 14082026 28082026 --details 20` y
`phase0_compare.py --n 15`. 3 listados + 35 detalles, todos HTTP 200.

| aspecto | hallazgo |
|---|---|
| error de ticket | ticket inválido → HTTP 203 con `{"Codigo":203,"Mensaje":"Ticket no válido."}`, no un 4xx. `api_client.py` debe validar `Codigo` en el cuerpo |
| listado | solo 4 campos: `CodigoExterno`, `Nombre`, `CodigoEstado`, `FechaCierre`. Trae todos los estados |
| filtro `fecha` | [Probable] no es fecha de publicación: las adjudicadas/desiertas aparecen el día de `FechaAdjudicacion` y las cerradas el de `FechaCierre`. Aparecen licitaciones de 2024 resueltas en 2026-08. El 01-08 (sábado) trae 3 filas |
| detalle | anidado: `Comprador.*`, `Fechas.*`, `Adjudicacion.*`, `Items.Listado[]` |
| ofertas | **el detalle no trae ofertas perdedoras**: solo `Items.Listado[].Adjudicacion` (RUT, nombre, cantidad, monto unitario del adjudicado) y `Adjudicacion.NumeroOferentes`. Las ofertas por proveedor solo están en la masiva |
| monto oculto | con `VisibilidadMonto = 0` la API devuelve `MontoEstimado = null`, **pero la masiva sí lo trae** (3 de 3 casos) |
| datos personales | el detalle trae nombres de funcionarios (`NombreUsuario`, `NombreResponsablePago`, `NombreResponsableContrato`) y campos de email/fono |
| consistencia | `CodigoEstado` coincide con la masiva en 19 de 19 licitaciones comunes |

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

### Montos: notación científica sin pérdida de precisión

`MontoEstimado` viene en notación científica con coma decimal en el 41 % de las
filas (`1,4e+07`). **No es redondeo**: en 12 de 12 licitaciones contrastadas con la
API el valor coincide exactamente (`1,79e+08` = 179.000.000). Es el formato con que
se exporta un número redondo (montos estimados suelen ser cifras cerradas). Ver
`scripts/phase0_compare.py`.

[Probable] La regla generaliza: no se observaron valores científicos con más de 5
dígitos significativos, consistente con un exportador que elige la representación
más corta.

| columna | entero | coma decimal | científica | NA |
|---|---|---|---|---|
| `MontoEstimado` | 85.127 | 262 | 59.682 | 15 |
| `Monto Estimado Adjudicado` | 92.464 | 0 | 3.610 | 49.012 |
| `MontoLineaAdjudica` | 144.435 | 102 | 549 | 0 |
| `MontoUnitarioOferta` | 140.138 | 2.242 | 2.706 | 0 |
| `Valor Total Ofertado` | 139.142 | 1.193 | 4.751 | 0 |

El parser de staging debe aceptar los tres formatos (`int`, `1234,5`, `1,4e+07`).

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

La masiva es la fuente principal: trae ofertas, montos ocultos en la API y se baja
con un request por mes, sin ticket ni cupo. La API queda para el incremental
(estados que cambian después de generado el archivo mensual) usando el listado por
`fecha` para detectar licitaciones resueltas ese día.
