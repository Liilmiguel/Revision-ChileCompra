# Plan del repositorio

```
.
├── Makefile                 # up, backfill, incremental, dbt, snapshot, dashboard, test
├── docker-compose.yml       # PostgreSQL 16
├── pyproject.toml / uv.lock
├── .env.example             # MERCADO_PUBLICO_TICKET (el .env real está en .gitignore)
├── src/observatorio/
│   ├── api_client.py        # httpx + reintentos/backoff + rate limit + enmascarado del ticket
│   ├── bulk.py              # descarga masiva mensual (backfill histórico), si la Fase 0 la valida
│   ├── backfill.py          # cupo diario configurable, reanudable vía extraction_log
│   └── load_raw.py          # upsert a raw.* (jsonb + extracted_at) por CodigoExterno
├── sql/init/                # DDL de schema raw y raw.extraction_log
├── dbt/                     # staging → intermediate → marts (+ tests y docs)
├── analysis/                # Fase 3: script que responde las 4 preguntas, con SQL
├── dashboard/               # Fase 4: Streamlit leyendo un snapshot parquet
├── tests/                   # pytest con fixtures redactadas desde data/samples
├── scripts/                 # exploración Fase 0
├── docs/                    # plan, mapeo de nombres, diccionario oficial resumido
└── data/samples/            # muestras crudas (ignoradas por git: datos de funcionarios)
```

Datos personales: las muestras crudas no se commitean. Los fixtures de tests
se generan redactando los campos de contacto (Fase 1).
