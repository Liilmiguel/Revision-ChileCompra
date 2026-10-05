# Observatorio de compras públicas (Mercado Público / ChileCompra)

Pipeline de licitaciones de Mercado Público hacia PostgreSQL.

- **Fase 0** (exploración): `docs/fase0_hallazgos.md`, scripts en `scripts/`.
- **Fase 1** (ingesta a `raw`): este README y `docs/fase1_ingesta.md`.

## Uso local

Requisitos: [uv](https://docs.astral.sh/uv/) y Docker (o una PostgreSQL 16 propia en `DATABASE_URL`).

```bash
cp .env.example .env          # pon tu MERCADO_PUBLICO_TICKET
uv sync
make up                       # PostgreSQL en localhost:5432
make backfill FROM=2025-1     # descarga masiva mensual, hasta el mes actual
make incremental              # detalles de la API de ayer (DAY=2026-10-04 para otro día)
make status                   # qué está cargado
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
Refresca los últimos meses de la descarga masiva y carga el incremental de la API de ayer.

## Datos personales

El detalle de la API trae nombres de funcionarios y la masiva RUT/nombre de proveedores
(que pueden ser personas naturales). Quedan solo en la base; las muestras en
`data/samples/` y `data/raw/` no se commitean y el fixture de tests está redactado.
