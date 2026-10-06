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
- **Señales de alerta**: oferente único; adjudicado más de 20 % sobre lo estimado;
  plazo de recepción de ofertas en el 10 % más corto de su tipo de licitación. Una
  señal **no prueba** una irregularidad: indica dónde revisar el expediente.

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
