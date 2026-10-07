FROM ?= 2025-1
TO ?=
DAY ?=

.PHONY: up down init backfill incremental status dbt dbt-full snapshot analysis dashboard vivo compras precios web test lint

up:  ## levanta PostgreSQL y espera a que acepte conexiones
	docker compose up -d --wait db

down:
	docker compose down

init:
	uv run observatorio init-db

backfill:  ## make backfill FROM=2024-1 TO=2026-9
	uv run observatorio backfill --from $(FROM) $(if $(TO),--to $(TO))

incremental:  ## make incremental DAY=2026-10-04 (por defecto, ayer)
	uv run observatorio incremental $(if $(DAY),--from $(DAY))

status:
	uv run observatorio status

dbt:  ## modela staging → intermediate → marts y corre los tests de datos
	cd dbt && DBT_PROFILES_DIR=. uv run --group dbt dbt build

dbt-full:  ## reconstruye todo, incluidas las tablas incrementales
	cd dbt && DBT_PROFILES_DIR=. uv run --group dbt dbt build --full-refresh

snapshot:  ## exporta los marts a data/snapshot/*.parquet
	uv run --group dashboard observatorio snapshot

analysis:  ## responde las 4 preguntas en docs/fase3_respuestas.md
	uv run --group dashboard python analysis/responder.py

dashboard:  ## abre el dashboard en http://localhost:8501
	uv run --group dashboard streamlit run dashboard/app.py

vivo:  ## licitaciones en curso: abiertas (API) y en evaluación (masiva) → data/vivo/vivo.json
	uv run observatorio vivo

compras:  ## Compras Ágiles y tratos directos de los últimos 12 meses → data/compras/compras.json
	uv run observatorio compras

precios:  ## precios unitarios de órdenes de compra (12 meses) → data/compras/precios.json
	uv run observatorio precios

web:  ## exporta data/web/ para la versión web (claude.ai) y verifica sus métricas contra Python
	uv run --group dashboard python dashboard/web/exportar.py
	uv run --group dashboard python dashboard/web/verificar.py

test:
	uv run pytest -q

lint:
	uv run ruff check . && uv run ruff format --check .
