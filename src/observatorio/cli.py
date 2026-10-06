"""Línea de comandos: `observatorio {init-db,backfill,incremental,status,snapshot}`."""

from __future__ import annotations

import argparse
import logging
from datetime import date, timedelta

from observatorio import bulk, config, load_raw, pipeline
from observatorio.api_client import MercadoPublicoClient


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="observatorio")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init-db", help="crea el schema raw")

    p_back = sub.add_parser("backfill", help="carga meses de la descarga masiva")
    p_back.add_argument("--from", dest="start", required=True, help="mes inicial AAAA-M")
    p_back.add_argument("--to", dest="end", help="mes final AAAA-M (por defecto, el actual)")
    p_back.add_argument("--force", action="store_true", help="recarga aunque el zip remoto no haya cambiado")
    p_back.add_argument("--keep-zip", action="store_true", help="conserva los zip en data/raw/")

    p_inc = sub.add_parser("incremental", help="carga detalles de la API por día de evento")
    p_inc.add_argument("--from", dest="start", type=date.fromisoformat, help="AAAA-MM-DD (por defecto, ayer)")
    p_inc.add_argument("--to", dest="end", type=date.fromisoformat, help="AAAA-MM-DD (por defecto, igual a --from)")
    p_inc.add_argument("--force", action="store_true")

    sub.add_parser("status", help="resumen de la bitácora de extracciones")

    p_snap = sub.add_parser("snapshot", help="exporta los marts a Parquet para el dashboard")
    p_snap.add_argument("--desde", default="2024-01-01", help="fecha de publicación mínima AAAA-MM-DD")

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    with load_raw.connect(config.database_url()) as conn:
        load_raw.init_db(conn)
        if args.command == "backfill":
            today = date.today()
            months = bulk.months_between(args.start, args.end or bulk.month_key(today.year, today.month))
            results = pipeline.backfill(conn, months, config.raw_dir(), force=args.force, keep_zip=args.keep_zip)
            _print(results)
        elif args.command == "incremental":
            start = args.start or date.today() - timedelta(days=1)
            days = pipeline.days_between(start, args.end or start)
            with MercadoPublicoClient(config.ticket()) as client:
                _print(pipeline.incremental(conn, client, days, force=args.force))
        elif args.command == "snapshot":
            from observatorio import snapshot

            counts = snapshot.export(conn, config.ROOT / "data" / "snapshot", args.desde)
            _print({k: f"{v} filas" for k, v in counts.items()})
        elif args.command == "status":
            for source, ok, errors, last in pipeline.status(conn):
                print(f"{source:12} {ok:5} cargados  {errors:3} errores  última: {last:%Y-%m-%d %H:%M}")
        else:
            print("schema raw listo")


def _print(results: dict[str, str]) -> None:
    for key, result in results.items():
        print(f"{key}: {result}")


if __name__ == "__main__":
    main()
