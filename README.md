# Observatorio de compras públicas (Mercado Público / ChileCompra)

Pipeline de licitaciones de Mercado Público hacia PostgreSQL.

- **Fase 0** (exploración): `docs/fase0_hallazgos.md`, scripts en `scripts/`.
- **Fase 1** (ingesta a `raw`): este README y `docs/fase1_ingesta.md`.
- **Fase 2** (modelado con dbt: staging → intermediate → marts): `docs/fase2_modelado.md`.
- **Fase 3** (las 4 preguntas): definiciones en `docs/fase3_preguntas.md`, respuestas en
  `docs/fase3_respuestas.md` (generadas por `analysis/responder.py`).
- **Fase 4** (dashboard Streamlit sobre un snapshot Parquet): `dashboard/app.py`.
  Versión web estática (métricas en el navegador, mismas definiciones): `dashboard/web/`,
  publicada en https://claude.ai/artifact/GrRmCFATYQQmaE7M9WtgWp. `make web` regenera
  sus datos y verifica que las métricas en JavaScript coincidan con las de Python.
  Pestaña **En curso**: licitaciones abiertas y en evaluación con señales tempranas y
  ofertas anormalmente bajas (`make vivo`, no usa la base; ver `docs/fase3_preguntas.md`).

## Uso local

Requisitos: [uv](https://docs.astral.sh/uv/) y Docker (o una PostgreSQL 16 propia en `DATABASE_URL`).
Si Docker Hub responde `429 Too Many Requests`, define `POSTGRES_IMAGE=mirror.gcr.io/library/postgres:16` en `.env`.

```bash
cp .env.example .env          # pon tu MERCADO_PUBLICO_TICKET
uv sync
make up                       # PostgreSQL en localhost:5432
make backfill FROM=2025-1     # descarga masiva mensual, hasta el mes actual
make incremental              # detalles de la API de ayer, ~50 min por día hábil (DAY=2026-10-04 para otro día)
make status                   # qué está cargado
make dbt                      # modelos staging → marts y tests de datos
make snapshot                 # exporta los marts a data/snapshot/*.parquet
make analysis                 # reescribe docs/fase3_respuestas.md
make dashboard                # http://localhost:8501
make vivo                     # licitaciones en curso → data/vivo/vivo.json (hasta 1.500 detalles nuevos de la API, ~1 h)
make compras                  # Compras Ágiles y tratos directos (12 meses) → data/compras/compras.json (~10 min)
make web                      # exporta data/web/ (incluye vivo.json) y verifica las métricas
make test lint
```

`backfill` es reanudable: salta los meses cuyo zip remoto no cambió (`Last-Modified`)
desde la última carga exitosa; `--force` recarga igual.

## Tablas

| tabla | contenido |
|---|---|
| `raw.bulk_licitacion` | primera fila del CSV masivo de cada licitación (todas las columnas, texto) |
| `raw.bulk_fila` | cada fila del CSV (licitación × ítem × oferta), solo columnas que difieren de la anterior |
| `raw.bulk_fila_completa` | vista que reconstruye la fila original exacta |
| `raw.api_licitacion` | último detalle de la API por `CodigoExterno` |
| `raw.extraction_log` | bitácora de extracciones (ok/error, filas, versión remota) |

## Ingesta programada

`.github/workflows/ingest.yml` corre a diario si el repo tiene los secrets
`DATABASE_URL` (una PostgreSQL accesible desde internet) y `MERCADO_PUBLICO_TICKET`.
Refresca los últimos meses de la descarga masiva, carga el incremental de la API de ayer
y corre `dbt build`.

## Datos personales

El detalle de la API trae nombres de funcionarios y la masiva RUT/nombre de proveedores
(que pueden ser personas naturales). Quedan solo en la base; las muestras en
`data/samples/` y `data/raw/` no se commitean y el fixture de tests está redactado.
