# Fase 3: respuestas

Generado por `analysis/responder.py` sobre el snapshot del 2026-10-06 (licitaciones publicadas entre 2024-01 y 2026-09). Definiciones y limitaciones en `docs/fase3_preguntas.md`; los mismos números se ven y filtran en el dashboard (`make dashboard`).

Universo: 322.040 licitaciones, 257.448 adjudicadas, 1.148 organismos, 44.137 proveedores adjudicados, $ 17.875 mil millones adjudicados en CLP.

**Quiebre en diciembre de 2024**: las licitaciones publicadas por mes caen de 13.361 (promedio enero–noviembre 2024) a 7.995 (promedio desde enero 2025). [Probable] Coincide con la entrada en vigencia de la Ley 21.634, que modernizó las compras públicas; comparar niveles antes y después de esa fecha mezcla dos regímenes.

## 1. Competencia: ¿cuántas empresas compiten por cada licitación?

**21,6 % de las 257.448 licitaciones adjudicadas tuvo un solo oferente.** La mediana es 3 oferentes (promedio 4,7).

| tipo | n | % oferente único | mediana |
|---|---|---|---|
| Privada < 100 UTM | 376 | 59,6 % | 1 |
| Servicios personales especializados | 72 | 58,3 % | 1 |
| Privada 2.000–5.000 UTM | 173 | 52,0 % | 1 |
| Privada 100–1.000 UTM | 1.828 | 48,8 % | 2 |
| Privada 1.000–2.000 UTM | 416 | 43,3 % | 2 |
| Privada ≥ 5.000 UTM | 114 | 40,4 % | 2 |
| Pública 100–1.000 UTM | 133.286 | 22,0 % | 3 |
| Pública 2.000–5.000 UTM | 15.324 | 21,1 % | 3 |
| Pública < 100 UTM | 63.318 | 20,9 % | 3 |
| Pública 1.000–2.000 UTM | 29.106 | 20,4 % | 3 |
| Pública ≥ 5.000 UTM | 11.583 | 19,6 % | 3 |
| Obra pública | 1.837 | 11,4 % | 4 |

## 2. Precio: ¿se adjudica por sobre o bajo lo estimado?

**La mediana adjudica 79 % del monto estimado** (219.015 licitaciones). 3,7 % supera lo estimado y 1,5 % lo supera en más de 20 %. Se excluye el 13,6 % de las adjudicadas con razón bajo 10 %: casi siempre convenios de suministro adjudicados por precio unitario, donde la razón no mide precio. La competencia baja el precio relativo:

| oferentes (10 = 10+) | n | mediana | p25 | p75 |
|---|---|---|---|---|
| 1 | 45.055 | 84 % | 79 % | 96 % |
| 2 | 40.603 | 82 % | 71 % | 86 % |
| 3 | 32.368 | 80 % | 67 % | 84 % |
| 4 | 23.237 | 77 % | 63 % | 84 % |
| 5 | 16.727 | 76 % | 61 % | 83 % |
| 6 | 12.430 | 73 % | 58 % | 83 % |
| 7 | 9.298 | 71 % | 56 % | 82 % |
| 8 | 7.290 | 70 % | 54 % | 81 % |
| 9 | 5.783 | 68 % | 52 % | 80 % |
| 10 | 26.224 | 65 % | 49 % | 78 % |

| tipo | n | mediana | % sobre estimado |
|---|---|---|---|
| Pública < 100 UTM | 59.493 | 78 % | 2,7 % |
| Pública 100–1.000 UTM | 112.925 | 79 % | 3,5 % |
| Pública 1.000–2.000 UTM | 22.374 | 80 % | 4,2 % |
| Pública 2.000–5.000 UTM | 11.455 | 80 % | 4,4 % |
| Pública ≥ 5.000 UTM | 8.623 | 80 % | 4,4 % |
| Servicios personales especializados | 67 | 100 % | 7,5 % |
| Privada < 100 UTM | 352 | 84 % | 3,7 % |
| Privada 100–1.000 UTM | 1.491 | 84 % | 5,8 % |
| Privada 1.000–2.000 UTM | 327 | 84 % | 4,6 % |
| Privada 2.000–5.000 UTM | 139 | 84 % | 5,0 % |
| Privada ≥ 5.000 UTM | 74 | 84 % | 12,2 % |
| Obra pública | 1.685 | 96 % | 36,3 % |

## 3. Concentración: ¿cuán concentradas están las compras?

A nivel país el mercado está repartido: los 10 mayores proveedores suman 8,2 % del monto en CLP entre 43.527 proveedores. **Dentro de cada organismo no**: 6 % de los 846 organismos con al menos 30 licitaciones adjudicadas tiene HHI > 2.500, y en la mediana su principal proveedor se lleva 17 % del monto.

Organismos más concentrados (con al menos 30 licitaciones):

| organismo | hhi | principal | proveedor principal | licitaciones |
|---|---|---|---|---|
| SERVICIO DE SALUD METROPOLITANO CENTRAL | 7.405 | 86 % | SACYR CHILE S.A. | 52 |
| I MUNICIPALIDAD DE SAN JOSE DE MAIPO | 6.218 | 78 % | ING MTV SPA | 45 |
| SERVICIO ELECTORAL | 6.004 | 77 % | TELEFONICA EMPRESAS CHILE SA | 90 |
| SERVIU REGION DE MAGALLANES Y DE LA ANTARTICA CHILENA | 5.965 | 76 % | CONSTRUCTORA SALFA S.A | 48 |
| SERVICIO DE SALUD ATACAMA | 5.818 | 76 % | Moller | 190 |
| SUBSECRETARIA DE EVALUACION SOCIAL | 5.407 | 73 % | FEN Depto. Sistemas de Información y Auditoria | 63 |
| Servicio Nacional del Consumidor - SERNAC | 5.321 | 72 % | UPCOM DTS | 47 |
| SERVICIO DE SALUD AYSEN CARLOS IBANEZ DEL CAMPO | 5.311 | 72 % | SOCOJOL SPA | 164 |
| I MUNICIPALIDAD DE LITUECHE | 5.255 | 72 % | INGENIERIA Y CONSTRUCCION M.S.T. SpA | 257 |
| INSTITUTO NACIONAL DE DERECHOS HUMANOS | 4.794 | 67 % | EDENRED CHILE S.A. | 34 |
| JUNTA NACIONAL DE AUXILIO ESCOLAR Y BECA | 4.695 | 67 % | Pluxee Chile S.A. | 400 |
| CENTRO DE FORMACION TECNICA ESTATAL DE MAGALLANES Y ANTARTICA CHILENA | 4.403 | 65 % | CONSTRUCCIONES INDUSTRIALES ASJ | 32 |
| I MUNICIPALIDAD DE PALMILLA | 4.401 | 66 % | Berrsot SpA | 172 |
| I MUNICIPALIDAD DE HUALAIHUE | 4.013 | 62 % | CUMBRES INGENIERIA SPA | 124 |
| I MUNICIPALIDAD DE PINTO | 3.972 | 62 % | Arrayan | 156 |

## 4. Proceso: ¿cuántas fracasan y cuánto demoran?

De 288.632 licitaciones cerradas hace más de 120 días, **12,9 % quedó desierta** y 2,4 % fue revocada; 82,3 % se adjudicó y 2,5 % sigue sin resolución en los datos. Recepción de ofertas: mediana 10 días; del cierre a la adjudicación: 20 días.

| tipo | n | adjudicada | desierta | revocada | sin_resolver | dias_oferta | dias_adjudicar |
|---|---|---|---|---|---|---|---|
| Pública < 100 UTM | 71.821 | 84,1 % | 12,9 % | 1,8 % | 1,2 % | 7 | 13 |
| Pública 100–1.000 UTM | 145.102 | 83,4 % | 12,7 % | 2,2 % | 1,6 % | 10 | 18 |
| Pública 1.000–2.000 UTM | 31.655 | 81,3 % | 11,9 % | 2,8 % | 4,0 % | 20 | 31 |
| Pública 2.000–5.000 UTM | 18.330 | 83,6 % | 12,3 % | 3,3 % | 0,9 % | 20 | 37 |
| Pública ≥ 5.000 UTM | 14.229 | 76,4 % | 13,4 % | 4,1 % | 6,1 % | 32 | 47 |
| Servicios personales especializados | 74 | 83,8 % | 4,1 % | 4,1 % | 8,1 % | 30 | 19 |
| Privada < 100 UTM | 490 | 65,9 % | 31,4 % | 1,2 % | 1,4 % | 7 | 12 |
| Privada 100–1.000 UTM | 2.231 | 68,8 % | 27,7 % | 1,3 % | 2,2 % | 10 | 15 |
| Privada 1.000–2.000 UTM | 547 | 62,7 % | 31,1 % | 1,8 % | 4,4 % | 20 | 23 |
| Privada 2.000–5.000 UTM | 256 | 67,6 % | 28,5 % | 1,6 % | 2,3 % | 20 | 24 |
| Privada ≥ 5.000 UTM | 185 | 54,1 % | 32,4 % | 3,2 % | 10,3 % | 32 | 34 |
| Obra pública | 3.678 | 47,4 % | 8,4 % | 6,2 % | 38,0 % | 29 | 104 |
| Obra privada | 34 | 41,2 % | 41,2 % | 2,9 % | 14,7 % | 28 | 160 |

## Señales de alerta

Cada licitación adjudicada suma un puntaje de 0 a 100 con seis señales ponderadas (definiciones en `docs/fase3_preguntas.md`). **1.169 licitaciones tienen riesgo alto** (puntaje ≥ 40, 0,45 % de las adjudicadas) y suman $ 361 mil millones; 82.972 tienen riesgo medio, casi todas solo por oferente único.

| señal | peso | % de las adjudicadas |
|---|---|---|
| Oferente único | 25 | 21,6 % |
| Competencia descalificada | 25 | 6,1 % |
| Pagó 50 % más que la oferta más barata | 20 | 4,9 % |
| Adjudicado más de 20 % sobre lo estimado | 15 | 1,3 % |
| Plazo de ofertas muy corto | 10 | 9,2 % |
| Precio unitario más de 5 veces la referencia | 5 | 1,2 % |

### Proveedores con más monto en licitaciones de riesgo alto

Dependencia: parte de sus ingresos que viene de su organismo principal. Captura: parte del gasto de ese organismo que se lleva. Una fila aquí no implica irregularidad del proveedor: las señales describen cómo se hizo la licitación.

| proveedor | ganadas | riesgo alto | monto riesgo alto | % único | organismo principal | dependencia | captura | acompañantes |
|---|---|---|---|---|---|---|---|---|
| Remavesa S.A. | 4 | 2 | $ 58,5 mil millones | 75 % | MINISTERIO DE OBRAS PUBLICAS DIREC CION GRAL DE OO PP DCYF | 100 % | 8 % | 0 |
| CONSTRUCTORA TRICAM SpA. | 33 | 1 | $ 46,0 mil millones | 27 % | MINISTERIO DE OBRAS PUBLICAS DIREC CION GRAL DE OO PP DCYF | 100 % | 4 % | 2 |
| De Vicente Ingenieria y Construccion | 3 | 2 | $ 44,8 mil millones | 67 % | MINISTERIO DE OBRAS PUBLICAS DIREC CION GRAL DE OO PP DCYF | 100 % | 17 % | 0 |
| INGENIERIA Y CONSTRUCCION M.S.T. SpA | 7 | 2 | $ 13,0 mil millones | 14 % | MINISTERIO DE OBRAS PUBLICAS DIREC CION GRAL DE OO PP DCYF | 54 % | 6 % | 0 |
| Pavimentos Quilín Ltda. | 30 | 1 | $ 12,8 mil millones | 20 % | MINISTERIO DE OBRAS PUBLICAS DIREC CION GRAL DE OO PP DCYF | 53 % | 2 % | 0 |
| Apia SPA | 25 | 3 | $ 9,7 mil millones | 16 % | MINISTERIO DE OBRAS PUBLICAS DIREC CION GRAL DE OO PP DCYF | 96 % | 2 % | 0 |
| DISEÑOS, SERVICIOS Y CONSTRUCCIONES HIDROSYM LTDA | 4 | 1 | $ 9,1 mil millones | 0 % | I MUNICIPALIDAD DE RENCA | 49 % | 35 % | 0 |
| SONDA S.A. | 29 | 1 | $ 8,4 mil millones | 17 % | I MUNICIPALIDAD DE COPIAPO | 40 % | 28 % | 0 |
| Sodexho Chile S.A. | 4 | 1 | $ 6,3 mil millones | 25 % | DIRECCION DE ABASTECIMIENTO DE LA ARMADA | 100 % | 15 % | 0 |
| CONSTRUCTORA ALVIAL S.A. | 15 | 1 | $ 6,3 mil millones | 7 % | SERVICIO DE VIVIENDA Y URBANIZACION AREA METROPOLITANA | 43 % | 8 % | 0 |
| Bitumix S.A. | 58 | 2 | $ 5,3 mil millones | 26 % | MINISTERIO DE OBRAS PUBLICAS DIREC CION GRAL DE OO PP DCYF | 71 % | 5 % | 0 |
| Johnson & Johnson MedTech | 1108 | 1 | $ 4,8 mil millones | 17 % | SERVICIO DE SALUD ORIENTE HOSPITAL DEL SALVADOR | 10 % | 5 % | 0 |
| Constructora Raymar Ltda. | 3 | 2 | $ 4,8 mil millones | 67 % | MINISTERIO DE OBRAS PUBLICAS DIREC CION GRAL DE OO PP DCYF | 100 % | 12 % | 0 |
| Constructora FV SpA. | 6 | 1 | $ 4,4 mil millones | 17 % | MINISTERIO DE OBRAS PUBLICAS DIREC CION GRAL DE OO PP DCYF | 100 % | 2 % | 0 |
| SOCIEDAD CONSTRUCTORA HURTADO LTDA  | 9 | 2 | $ 3,7 mil millones | 56 % | SERVICIO DE VIVIENDA Y URBANIZACION X REGION | 40 % | 19 % | 0 |

### Organismos con mayor proporción de riesgo alto

| organismo | adjudicadas | % riesgo alto | % único | % descalificada |
|---|---|---|---|---|
| DELEGACIÓN PRESIDENCIAL PROVINCIAL DEL TAMARUGAL | 74 | 23,0 % | 25,7 % | 10,8 % |
| Ilustre Municipalidad de Ñiquen | 125 | 9,6 % | 18,4 % | 16,0 % |
| CORPORACION MUNICIPAL DE FOMENTO AL DESARROLLO COMUNAL Y PRODUCTIVO DE LA FLORIDA | 46 | 6,5 % | 30,4 % | 10,9 % |
| SERVICIO DE VIVIENDA Y URBANIZACION X REGION | 81 | 6,2 % | 23,5 % | 2,5 % |
| MINISTERIO DE OBRAS PUBLICAS DIREC CION GRAL DE OO PP DCYF | 104 | 5,8 % | 16,3 % | 3,8 % |
| I MUNICIPALIDAD DE CHONCHI | 168 | 5,4 % | 37,5 % | 13,1 % |
| I MUNICIPALIDAD DE PURRANQUE | 237 | 5,1 % | 21,1 % | 13,9 % |
| MINISTERIO DE OBRAS PUBLICAS DIREC CION GRAL DE OO PP DCYF | 192 | 4,7 % | 18,8 % | 5,7 % |
| SERVICIO SALUD ATACAMA HOSPITAL DE HUASCO | 107 | 4,7 % | 18,7 % | 1,9 % |
| I MUNICIPALIDAD DE MARIQUINA | 197 | 4,6 % | 19,8 % | 7,1 % |

Pares "acompañante" (ofertan juntos 5+ veces en licitaciones de 2 a 4 oferentes, uno gana 80 %+ y el otro nunca): 372. Pueden ser competencia simulada o mercados de nicho con pocos actores.
