"""Fase 0: compara la descarga masiva con el detalle de la API para los mismos CodigoExterno.

Toma del CSV masivo licitaciones cuyo MontoEstimado viene en notación científica,
pide su detalle a la API y escribe data/samples/COMPARE.md con ambos valores.

Uso: uv run python scripts/phase0_compare.py --month 2026-8 --n 15
"""

from __future__ import annotations

import argparse
import csv
import io
import random
import time
import zipfile

import httpx
from phase0_explore import API_BASE, PAUSE_SECONDS, SAMPLES, get_json, load_ticket, save


def bulk_rows(month: str) -> dict[str, dict]:
    """Primera fila de cada CodigoExterno del CSV masivo del mes."""
    rows: dict[str, dict] = {}
    with zipfile.ZipFile(SAMPLES / "bulk" / f"lic_{month}.zip") as z:
        name = z.namelist()[0]
        text = io.TextIOWrapper(z.open(name), encoding="cp1252", newline="")
        for row in csv.DictReader(text, delimiter=";"):
            rows.setdefault(row["CodigoExterno"], row)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--month", default="2026-8", help="mes AAAA-M ya descargado con phase0_explore.py")
    parser.add_argument("--n", type=int, default=15)
    args = parser.parse_args()

    rows = bulk_rows(args.month)
    sci = [c for c, r in rows.items() if "e+" in r["MontoEstimado"]]
    picked = random.Random(42).sample(sci, min(args.n, len(sci)))

    ticket = load_ticket()
    out = [
        f"# Masiva {args.month} vs. API ({len(picked)} licitaciones con MontoEstimado en notación científica)\n",
        "| CodigoExterno | masiva MontoEstimado | masiva VisibilidadMonto | API MontoEstimado "
        "| API VisibilidadMonto | estado masiva | estado API |",
        "|---|---|---|---|---|---|---|",
    ]
    with httpx.Client(base_url=API_BASE, timeout=60) as client:
        for code in picked:
            status, data = get_json(client, ticket, {"codigo": code})
            print(f"detalle {code}: HTTP {status}")
            api = (data or {}).get("Listado") or [{}]
            if data is not None:
                save(f"detail_{code}.json", data)
            b, a = rows[code], api[0]
            out.append(
                f"| {code} | {b['MontoEstimado']} | {b['VisibilidadMonto']} | {a.get('MontoEstimado')} "
                f"| {a.get('VisibilidadMonto')} | {b['CodigoEstado']} | {a.get('CodigoEstado')} |"
            )
            time.sleep(PAUSE_SECONDS)
    (SAMPLES / "COMPARE.md").write_text("\n".join(out) + "\n")
    print(f"escrito {SAMPLES / 'COMPARE.md'}")


if __name__ == "__main__":
    main()
