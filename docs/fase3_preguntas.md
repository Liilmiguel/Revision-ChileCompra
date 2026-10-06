# Metodología

## Las cuatro preguntas

Como el proyecto no traía preguntas definidas, se eligieron cuatro que (a) responden
a riesgos reconocidos en compras públicas —son los indicadores más usados por la OCDE
y por *Open Contracting Partnership* para detectar falta de competencia— y (b) se
pueden contestar con los datos disponibles sin supuestos fuertes.

| # | Pregunta | Indicador principal |
|---|---|---|
| 1 | **Competencia**: ¿cuántas empresas compiten por cada licitación? | % de adjudicadas con **un solo oferente** |
| 2 | **Precio**: ¿se adjudica por sobre o por debajo de lo estimado, y cambia con la competencia? | mediana de **adjudicado / estimado** |
| 3 | **Concentración**: ¿cuán concentradas están las compras de cada organismo en pocos proveedores? | **HHI** del monto adjudicado por organismo |
| 4 | **Proceso**: ¿cuántas licitaciones fracasan y cuánto demoran? | % **desiertas** y revocadas; días hasta adjudicar |

## Definiciones

- **Universo**: licitaciones publicadas desde enero de 2024 en la descarga masiva de
  Mercado Público, con el estado más reciente entre la descarga masiva y la API.
- **Adjudicada**: estados 8, 9 y 10 de ChileCompra. `FechaAdjudicacion` solo se usa en
  adjudicadas; en las demás la fuente trae una fecha estimada.
- **Oferentes**: proveedores distintos (`CodigoProveedor`) con oferta en la licitación.
  Se usa en vez de `NumeroOferentes` porque es verificable fila a fila. Se excluyen las
  adjudicadas sin ofertas registradas.
- **Adjudicado / estimado**: suma de las líneas adjudicadas dividida por el monto
  estimado, solo cuando ambos están en la misma moneda y el estimado es mayor que 0.
  El estimado suele ser un monto redondo y en muchas licitaciones es un tope
  presupuestario, así que valores bajo 100 % son esperables. Se excluyen las razones
  bajo 10 % (~14 % de las adjudicadas): casi siempre **convenios de suministro
  adjudicados por precio unitario** (fotocopias a $15 con un estimado de $28 millones),
  donde la razón no mide precio.
- **Líneas de monto atípico** (`int_linea_adjudicada`): errores de captura que se
  excluyen de todos los montos. Tres reglas:
  1. *cantidad*: cantidad adjudicada >100× lo ofertado y lo solicitado (9.597 líneas);
  2. *tope*: la línea vale >10× el tope legal de su tipo (L1 < 100 UTM, LE < 1.000…;
     UTM ≈ $70.000). Solo 39 líneas, pero sumaban **5,67 billones de pesos, ~24 % del
     monto del periodo**: p. ej. una L1 de la Universidad de Talca adjudicada en $5,25
     billones porque el estimado (3.000.000) se escribió como cantidad ofertada;
  3. *estimado*: la línea vale >10× un estimado creíble (≥ $1 millón) en la misma
     moneda (109 líneas).
  Sin estas reglas, el organismo "más concentrado" del país era la Universidad de Talca
  y los 10 mayores proveedores sumaban 28,6 % del monto; con ellas, 8,2 %.
- **HHI** (índice Herfindahl-Hirschman): suma de los cuadrados de la participación de
  cada proveedor en el monto adjudicado en CLP de un organismo, de 0 a 10.000. Sobre
  2.500 se considera concentración alta (umbral de las guías de fusiones de EE. UU.).
  Solo organismos con al menos 30 licitaciones adjudicadas.
- **Licitaciones maduras** (pregunta 4): cerradas hace más de 120 días. Así las
  recientes, que aún pueden adjudicarse, no inflan las tasas de fracaso.

## Señales de alerta y puntaje de riesgo

Cada licitación adjudicada recibe un **puntaje de 0 a 100** que suma seis señales
ponderadas (`dbt/models/intermediate/int_licitacion_senales.sql`; pesos en
`dbt_project.yml`, var `senales`). Las dos de competencia pesan más porque son las más
asociadas a direccionamiento en la literatura (indicadores de la OCDE y de Fazekas sobre
riesgo de corrupción en compras públicas).

| señal | peso | definición | % de las adjudicadas |
|---|---|---|---|
| Oferente único | 25 | un solo proveedor ofertó | 21,6 % |
| Competencia descalificada | 25 | hubo 2+ oferentes y todos menos el ganador fueron rechazados | 6,1 % |
| Pagó 50 % más que la oferta más barata | 20 | en líneas con 2+ ofertas aceptadas, lo pagado sobre la aceptada más barata es más de un tercio del monto (se ignoran ofertas "baratas" bajo 30 % de la ganadora, casi siempre errores como $1) | 4,9 % |
| Adjudicado más de 20 % sobre lo estimado | 15 | razón adjudicado / estimado > 1,2 en la misma moneda | 1,3 % |
| Plazo de ofertas muy corto | 10 | días de publicación a cierre en el 10 % más corto de su tipo | 9,2 % |
| Precio unitario más de 5 veces la referencia | 5 | precio ganador > 5 × mediana del mismo producto (código ONU × unidad), solo bienes con 30+ licitaciones y precios homogéneos (p75/p25 < 2,5) | 1,2 % |

- **Riesgo alto**: puntaje ≥ 40, es decir, al menos dos señales y una de ellas fuerte
  (1.169 licitaciones, 0,45 % de las adjudicadas). **Medio**: 20 a 39; casi siempre solo
  oferente único.
- Se descartaron dos candidatas por ruido: "la ganadora no es la más barata" por línea
  (28 % de las líneas comparables: muchas licitaciones evalúan calidad técnica) y precio
  de referencia sin restricciones (los códigos ONU son categorías amplias: 23 % de las
  líneas superaba 3 × la mediana).
- Una señal **no prueba** una irregularidad: indica dónde revisar el expediente.

### Por proveedor

Agregan las licitaciones adjudicadas que ganó cada proveedor (montos en CLP):

- **Riesgo alto** y **monto en riesgo alto**: cuántas de sus licitaciones tienen puntaje ≥ 40.
- **Dependencia**: parte de sus ingresos que viene de su organismo principal.
- **Captura**: parte del gasto de ese organismo que se lleva el proveedor.
- **Sin competencia en un organismo**: máximo de licitaciones ganadas como oferente único
  en un mismo organismo (relación recurrente sin competencia).
- **Acompañantes** (`fct_par_proveedores`): proveedores que ofertaron junto a él 5+ veces
  en licitaciones de 2 a 4 oferentes sin ganarle nunca, mientras él ganó 80 %+. Es la señal
  clásica de competencia simulada, pero también aparece en mercados de nicho (372 pares).
- **Tasa de éxito**: licitaciones ganadas / licitaciones en que ofertó en todo el periodo.

## Limitaciones

- **Montos de convenios de suministro**: se adjudican por precio unitario, así que su
  "monto adjudicado" subestima el valor real del contrato. Los totales en pesos y la
  concentración por monto subestiman a los proveedores de suministros.
- **Quiebre de diciembre de 2024**: las licitaciones mensuales caen de ~13.400 a ~8.000.
  [Probable] Entrada en vigencia de la Ley 21.634; las series que cruzan esa fecha
  mezclan dos regímenes.
- **Monedas**: los montos no se convierten. Las sumas de dinero usan solo CLP (~99 %
  de las ofertas); las razones comparan montos en la misma moneda.
- **Errores de captura**: además de las líneas atípicas, hay precios unitarios que en
  realidad son totales. Los rankings por monto deben revisarse a mano antes de citarse.
- **Meses recientes**: las licitaciones de los últimos meses siguen en evaluación; las
  series mensuales de adjudicación y plazos están incompletas al final.
- **Cobertura**: solo licitaciones (no órdenes de compra, convenio marco ni trato
  directo), que son solo una parte del gasto público total.
- Los tipos de licitación por tramo de UTM siguen la nomenclatura de ChileCompra
  (L1, LE, LP, LQ, LR, …).
