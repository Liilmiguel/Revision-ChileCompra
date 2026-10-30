"""Línea de comandos: `observatorio {init-db,backfill,incremental,status,snapshot,vivo,compras,precios}`."""

from __future__ import annotations

import argparse
import logging
from datetime import date, timedelta
from pathlib import Path

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

    p_vivo = sub.add_parser("vivo", help="licitaciones en curso (abiertas y en evaluación) para la versión web")
    p_vivo.add_argument("--max-detalles", type=int, default=1500, help="detalles nuevos a pedir a la API (~2,5 s c/u)")
    p_vivo.add_argument("--meses", type=int, default=4, help="meses recientes de la descarga masiva")
    p_vivo.add_argument("--semilla", type=Path, help="vivo.json anterior: reutiliza sus detalles de la API")

    p_compras = sub.add_parser("compras", help="Compras Ágiles y tratos directos (órdenes de compra) para la web")
    p_compras.add_argument("--meses", type=int, default=12, help="meses completos más recientes")

    p_precios = sub.add_parser("precios", help="comparación de precios unitarios en órdenes de compra para la web")
    p_precios.add_argument("--meses", type=int, default=12, help="meses completos más recientes")

    p_vinc = sub.add_parser("vinculos", help="grupos de proveedores que comparten dirección o contacto")
    p_vinc.add_argument("--max-consultas", type=int, default=6000, help="consultas nuevas a la API (~2,5 s c/u)")

    p_ip = sub.add_parser("infoprobidad", help="participaciones en sociedades desde datos.cplt.cl")
    p_ip.add_argument(
        "--fichas", type=Path, help="extracción previa de infoprobidad.cl, para enlazar las declaraciones"
    )

    p_conf = sub.add_parser("conflictos", help="participaciones de funcionarios (InfoProbidad) en proveedores")
    p_conf.add_argument("participaciones", type=Path, help="JSON de participaciones extraído de InfoProbidad")
    p_conf.add_argument("--lic", type=Path, help="lic_org_rut.json de una corrida con base: no usa la base de datos")

    args = parser.parse_args(argv)
    if args.command == "infoprobidad":
        from observatorio import infoprobidad

        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
        logging.getLogger("httpx").setLevel(logging.WARNING)
        _print({k: str(v) for k, v in infoprobidad.generar(config.ROOT / "data" / "infoprobidad", args.fichas).items()})
        return
    if args.command == "conflictos" and args.lic:
        from observatorio import conflictos

        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
        out = config.ROOT / "data" / "compras"
        r = conflictos.generar(None, args.participaciones, out, config.raw_dir(), args.lic)
        _print({k: str(v) for k, v in r.items()})
        return
    if args.command == "precios":
        from observatorio import precios

        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
        _print(
            {
                k: str(v)
                for k, v in precios.generar(config.ROOT / "data" / "compras", config.raw_dir(), args.meses).items()
            }
        )
        return
    if args.command == "compras":
        from observatorio import compras

        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
        r = compras.generar(config.ROOT / "data" / "compras", config.raw_dir(), args.meses)
        _print({k: str(v) for k, v in r.items()})
        return
    if args.command == "vivo":
        # No usa la base de datos: corre también en una sesión sin PostgreSQL.
        import os

        from observatorio import vivo

        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
        ticket = os.environ.get("MERCADO_PUBLICO_TICKET") or None
        r = vivo.generar(
            config.ROOT / "data" / "vivo", config.raw_dir(), ticket, args.max_detalles, args.meses, args.semilla
        )
        _print({k: str(v) for k, v in r.items()})
        return

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
        elif args.command == "vinculos":
            import os

            from observatorio import vinculos

            ticket = os.environ.get("MERCADO_PUBLICO_TICKET") or None
            r = vinculos.generar(conn, config.ROOT / "data" / "compras", config.raw_dir(), ticket, args.max_consultas)
            _print({k: str(v) for k, v in r.items()})
        elif args.command == "conflictos":
            from observatorio import conflictos

            out = config.ROOT / "data" / "compras"
            _print(
                {k: str(v) for k, v in conflictos.generar(conn, args.participaciones, out, config.raw_dir()).items()}
            )
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
