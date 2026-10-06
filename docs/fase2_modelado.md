# Fase 2: modelado (dbt)

Estado al 2026-10-06. Verificado sobre 5 meses de la masiva (2007-1, 2016-6, 2024-1,
2026-8, 2026-9: 75.269 licitaciones, 1,6 M ofertas) y 1.208 detalles de la API.

```bash
make dbt        # dbt build: modelos + 36 tests de datos
make dbt-full   # reconstruye también la tabla incremental
```

## Capas

| capa | modelo | grano | notas |
|---|---|---|---|
| staging | `stg_bulk__licitacion` | licitación | vista; tipado y renombre de columnas entre épocas |
| staging | `stg_bulk__oferta` | fila del CSV (licitación × ítem × oferta) | tabla **incremental** por `source_month`: solo reprocesa meses recargados |
| staging | `stg_api__licitacion` | licitación | estado y fechas del detalle de la API |
| intermediate | `int_licitacion` | licitación | estado actual: API si su detalle es posterior a la masiva |
| intermediate | `int_licitacion__ofertas` | licitación | conteos de oferentes, líneas y montos adjudicados |
| marts | `fct_licitacion` | licitación | tabla principal para análisis |
| marts | `fct_oferta` | oferta | vista sobre staging (no duplica 1,6 M filas) |
| marts | `dim_organismo`, `dim_proveedor` | organismo / proveedor | nombre más reciente y totales |
| seeds | `ref.moneda`, `ref.estado_licitacion` | — | catálogos verificados con los datos |

## Reglas de tipado (macros en `dbt/macros/parse.sql`)

- Números: `123`, `1234,5` y `1,4e+07`. El test `valores_no_parseados` falla si un valor
  informado en raw no calza: hoy 0 en las 5 épocas.
- Fechas: `AAAA-MM-DD`; `1900-01-01` es el centinela de "sin fecha".
- `MontoEstimado = 0` (común en 2007) se trata como no informado.
- Columnas renombradas entre épocas (`Nombre producto genérico` / `genrico`, etc.) se
  leen con `coalesce` de ambas variantes.
- Estados: 8, 9 y 10 = Adjudicada; 6, 11–14 = Cerrada; 7 Desierta; 15 Revocada;
  16 Suspendida; 5 Publicada (solo API).
- Monedas de oferta: `Peso Chileno`→CLP, `Dolar`/`Dólar`→USD, `Unidad de Fomento`→CLF,
  `Euro`→EUR, `Moneda revisar`→UTM (a nivel licitación `Moneda revisar` siempre es UTM;
  [Probable] lo mismo en ofertas). **Los montos no se convierten a CLP**: ~99 % están en
  CLP y los marts solo suman montos de una misma moneda.

## Hallazgos de esta fase

1. **Cantidades adjudicadas absurdas.** En 4.993 de 302.111 ofertas adjudicadas la
   cantidad adjudicada supera a la ofertada. La mayoría es plausible (servicio ofertado
   como 1 unidad y adjudicado por 12 meses), pero algunas son un monto escrito en el campo
   cantidad: una línea solicitada 1 vez con 287.165.982 unidades adjudicadas vale
   7,9×10¹⁶ CLP. Sumando sin filtro, el total adjudicado de 2016-6 da 8,8×10¹⁶ CLP (~88.300
   billones de pesos); excluyendo las líneas con cantidad adjudicada >100× lo ofertado y lo
   solicitado (`cantidad_adjudicada_atipica`, 888 líneas en 5 meses) da 205 mil millones.
   `fct_licitacion.monto_adjudicado` las excluye; `monto_adjudicado_bruto` las incluye.
2. **Quedan errores que la regla no detecta**: p. ej. un precio unitario que en realidad
   es el total (bancos escolares a 22 millones c/u × 1.259 = 27.900 millones). Antes de
   publicar rankings por monto hay que revisar a mano los mayores valores.
3. **`NumeroOferentes` ≠ proveedores distintos en la masiva** en 7.810 licitaciones
   (5.006 solo en 2007). `n_proveedores_oferentes` cuenta `CodigoProveedor` distintos
   del CSV; `numero_oferentes` es el campo de origen. Elegir uno según la pregunta.
4. **La API corrige el estado de meses abiertos**: en 2026-8 y 2026-9, 559 licitaciones
   toman el estado de la API (más reciente que el zip).
5. **El archivo de 2026-3 viene dañado en origen** (mismo MD5 en dos descargas; el zip
   pasa su verificación de integridad): hay bytes sobrescritos dentro del texto
   (`"P"DRO LAGOS`, `Peso nhileno`, `8210a`). Las comillas sueltas desarman 849 registros
   (0,5 %), que el lector descarta y anota en `raw.extraction_log`; si un mes supera el
   2 %, falla completo. Los valores ilegibles que sí entran (11 monedas, 5 números)
   quedan nulos en staging; los tests `valores_no_parseados` y `moneda_oferta_conocida`
   avisan desde 1 caso y fallan sobre 50. **También hay dígitos cambiados por otros
   dígitos**, que solo se detectan cuando un test cruza dos campos: en 1058125-3-LE26,
   3.490 × 20 = 69.800 pero la línea dice 59.800 (`monto_linea_consistente`). Los montos
   de 2026-3 son menos confiables que los del resto.
6. **Rendimiento**: sin `materialized` en el CTE, PostgreSQL recalculaba la fusión de
   jsonb por cada columna (>18 min); con él, 2,5 min para 1,6 M filas. Las corridas
   siguientes solo procesan meses recargados (0,4 s si no hay cambios).

## Panorama de los 5 meses cargados

| mes | licitaciones | % adjudicadas | % oferente único (adjudicadas) | mediana adjudicado/estimado |
|---|---|---|---|---|
| 2007-1 | 35.087 | 87,9 | 17,8 | 0,83 |
| 2016-6 | 15.827 | 86,2 | 19,1 | 0,76 |
| 2024-1 | 11.712 | 84,7 | 23,6 | 0,74 |
| 2026-8 | 8.142 | 49,9 | 22,4 | 0,76 |
| 2026-9 | 4.501 | 24,5 | 30,9 | 0,81 |

2026-8 y 2026-9 siguen abiertos (muchas licitaciones aún cerradas sin adjudicar).

## Pendiente

- Los marts de la Fase 3 dependen de las 4 preguntas del análisis, que no están en el
  repositorio. `fct_licitacion` y `fct_oferta` cubren preguntas de competencia
  (oferente único), eficiencia (adjudicado vs. estimado) y concentración (proveedor ×
  organismo), pero no hay marts específicos por pregunta.
- Conversión de USD/CLF/UTM a CLP (requiere series diarias del Banco Central o CMF).
