"""Fase 0: descarga muestras de la API de Mercado Público y de la descarga masiva.

Uso:
    uv run python scripts/phase0_explore.py --dates 01092026 02092026 03092026 --details 20
    uv run python scripts/phase0_explore.py --bulk-month 2026-8

Las respuestas quedan en data/samples/ (ignorado por git: el detalle trae
datos de contacto de funcionarios). El ticket nunca se imprime.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from pathlib import Path

import httpx

API_BASE = "https://api.mercadopublico.cl/servicios/v1/publico/"
BULK_BASE = "https://transparenciachc.blob.core.windows.net/lic-da/"
SAMPLES = Path(__file__).resolve().parents[1] / "data" / "samples"
PAUSE_SECONDS = 2.0  # la API rechaza peticiones simultáneas; vamos de a una


def load_ticket() -> str:
    env_file = Path(__file__).resolve().parents[1] / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            key, _, value = line.partition("=")
            if key.strip() == "MERCADO_PUBLICO_TICKET" and value.strip():
                os.environ.setdefault("MERCADO_PUBLICO_TICKET", value.strip())
    ticket = os.environ.get("MERCADO_PUBLICO_TICKET", "")
    if not ticket:
        sys.exit("Falta MERCADO_PUBLICO_TICKET (en .env o en el entorno).")
    return ticket


def mask(text: str, ticket: str) -> str:
    return text.replace(ticket, "***") if ticket else text


def get_json(client: httpx.Client, ticket: str, params: dict) -> tuple[int, dict | None]:
    for attempt in range(4):
        try:
            resp = client.get("licitaciones.json", params={**params, "ticket": ticket})
            if resp.status_code < 500:
                return resp.status_code, resp.json()
            print(f"  HTTP {resp.status_code}, reintento {attempt + 1}")
        except (httpx.HTTPError, ValueError) as exc:
            print(f"  error: {mask(str(exc), ticket)}, reintento {attempt + 1}")
        time.sleep(2 ** (attempt + 1))
    return 0, None


def save(name: str, payload: object) -> None:
    SAMPLES.mkdir(parents=True, exist_ok=True)
    (SAMPLES / name).write_text(json.dumps(payload, ensure_ascii=False, indent=2))


def explore_api(dates: list[str], n_details: int) -> None:
    ticket = load_ticket()
    codes_by_state: dict[str, list[str]] = {}
    with httpx.Client(base_url=API_BASE, timeout=60) as client:
        for date in dates:
            status, data = get_json(client, ticket, {"fecha": date})
            print(f"listado {date}: HTTP {status}, {data.get('Cantidad') if data else '-'} filas")
            if data is None:
                continue
            save(f"listing_{date}.json", data)
            for row in data.get("Listado", []):
                codes_by_state.setdefault(str(row.get("CodigoEstado")), []).append(row["CodigoExterno"])
            time.sleep(PAUSE_SECONDS)

        # Muestra estratificada por estado, con sobrepeso en adjudicadas (8),
        # que son las que responden las preguntas 1-4.
        rng = random.Random(42)
        picked: list[str] = []
        adjudicadas = codes_by_state.get("8", [])
        picked += rng.sample(adjudicadas, min(len(adjudicadas), n_details // 2))
        others = [c for s, cs in codes_by_state.items() if s != "8" for c in cs]
        picked += rng.sample(others, min(len(others), n_details - len(picked)))

        for code in picked:
            status, data = get_json(client, ticket, {"codigo": code})
            print(f"detalle {code}: HTTP {status}")
            if data is not None:
                save(f"detail_{code}.json", data)
            time.sleep(PAUSE_SECONDS)


def download_bulk(month: str) -> None:
    """month en formato AAAA-M (sin cero a la izquierda, como publica ChileCompra)."""
    target = SAMPLES / "bulk" / f"lic_{month}.zip"
    target.parent.mkdir(parents=True, exist_ok=True)
    with httpx.stream("GET", f"{BULK_BASE}{month}.zip", timeout=600, follow_redirects=True) as resp:
        print(f"bulk {month}: HTTP {resp.status_code}")
        resp.raise_for_status()
        with target.open("wb") as fh:
            for chunk in resp.iter_bytes():
                fh.write(chunk)
    print(f"guardado {target} ({target.stat().st_size / 1e6:.1f} MB)")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dates", nargs="*", default=[], help="fechas DDMMAAAA")
    parser.add_argument("--details", type=int, default=20)
    parser.add_argument("--bulk-month", help="mes AAAA-M de la descarga masiva")
    args = parser.parse_args()
    if args.dates:
        explore_api(args.dates, args.details)
    if args.bulk_month:
        download_bulk(args.bulk_month)


if __name__ == "__main__":
    main()
