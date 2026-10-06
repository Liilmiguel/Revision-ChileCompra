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

Adjudicadas según cuántas señales acumulan (oferente único, >20 % sobre estimado, plazo en el 10 % más corto de su tipo):

| senales | n |
|---|---|
| 0 | 181.936 |
| 1 | 68.485 |
| 2 | 6.940 |
| 3 | 87 |
