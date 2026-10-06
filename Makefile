FROM ?= 2025-1
TO ?=
DAY ?=

.PHONY: up down init backfill incremental status dbt dbt-full test lint

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

test:
	uv run pytest -q

lint:
	uv run ruff check . && uv run ruff format --check .
