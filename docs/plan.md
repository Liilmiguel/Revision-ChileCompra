# Plan del repositorio

```
.
├── Makefile                 # up, backfill, incremental, dbt, snapshot, dashboard, test
├── docker-compose.yml       # PostgreSQL 16
├── pyproject.toml / uv.lock
├── .env.example             # MERCADO_PUBLICO_TICKET (el .env real está en .gitignore)
├── src/observatorio/
│   ├── api_client.py        # httpx + reintentos/backoff + rate limit + enmascarado del ticket
│   ├── bulk.py              # descarga masiva mensual (fuente principal, backfill histórico)
│   ├── load_raw.py          # escritura en raw.* y bitácora raw.extraction_log
│   ├── pipeline.py          # backfill (masiva, reanudable por Last-Modified) e incremental (API)
│   └── cli.py               # `observatorio {init-db,backfill,incremental,status}`
├── sql/init/                # DDL de schema raw y raw.extraction_log
├── .github/workflows/       # ci (tests con PostgreSQL) e ingest (diaria, con secrets)
├── dbt/                     # staging → intermediate → marts (+ tests y docs), ver docs/fase2_modelado.md
├── analysis/                # Fase 3: responder.py escribe docs/fase3_respuestas.md
├── dashboard/               # Fase 4: Streamlit sobre data/snapshot/*.parquet (métricas en src/observatorio/metricas.py)
├── tests/                   # pytest con fixtures redactadas desde data/samples
├── scripts/                 # exploración Fase 0
├── docs/                    # plan, mapeo de nombres, diccionario oficial resumido
└── data/samples/            # muestras crudas (ignoradas por git: datos de funcionarios)
```

Datos personales: las muestras crudas no se commitean. Los fixtures de tests
se generan redactando los campos de contacto (Fase 1).
