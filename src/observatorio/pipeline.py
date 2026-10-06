"""Orquestación: backfill desde la descarga masiva e incremental desde la API."""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import httpx
import psycopg

from observatorio import bulk, load_raw
from observatorio.api_client import ApiError, MercadoPublicoClient

log = logging.getLogger(__name__)


def backfill(
    conn: psycopg.Connection,
    months: list[str],
    raw_dir: Path,
    *,
    force: bool = False,
    keep_zip: bool = False,
) -> dict[str, str]:
    """Carga cada mes de la descarga masiva. Salta los meses cuyo zip remoto no cambió
    desde la última carga exitosa, así que se puede re-ejecutar para reanudar o refrescar."""
    results: dict[str, str] = {}
    with httpx.Client(timeout=600) as http:
        for month in months:
            started = datetime.now(UTC)
            try:
                version = bulk.remote_version(month, http)
                if version is None:
                    results[month] = "no publicado"
                    continue
                previous = load_raw.last_ok(conn, "bulk", month)
                if previous and previous[1] == version and not force:
                    results[month] = "sin cambios"
                    continue
                log.info("descargando %s", month)
                zip_path = bulk.download(month, raw_dir, http)
                stats: dict = {}
                n = load_raw.replace_bulk_month(conn, month, bulk.read_rows(zip_path, stats))
                nota = f"{stats['malformados']} registros malformados descartados" if stats.get("malformados") else None
                load_raw.log_extraction(
                    conn, "bulk", month, "ok", rows=n, remote_version=version, error=nota, started_at=started
                )
                if not keep_zip:
                    zip_path.unlink()
                results[month] = f"{n} filas" + (f" ({nota})" if nota else "")
            except Exception as exc:  # noqa: BLE001 - se registra y se sigue con el próximo mes
                conn.rollback()
                load_raw.log_extraction(conn, "bulk", month, "error", error=str(exc)[:2000], started_at=started)
                results[month] = f"error: {exc}"
            log.info("%s: %s", month, results[month])
    return results


def days_between(start: date, end: date) -> list[date]:
    return [start + timedelta(days=i) for i in range((end - start).days + 1)]


def incremental(
    conn: psycopg.Connection,
    client: MercadoPublicoClient,
    days: list[date],
    *,
    force: bool = False,
    today: date | None = None,
    batch_size: int = 50,
) -> dict[str, str]:
    """Para cada día, pide el listado de la API y el detalle de cada licitación listada.

    Un día hábil trae ~1.200 licitaciones (~50 min), así que los detalles se guardan
    en lotes y, al reanudar, se saltan los ya descargados después de ese día (ya
    reflejan el evento). Un día ya cargado se salta salvo `force`, excepto hoy y
    ayer, que pueden seguir recibiendo eventos."""
    today = today or date.today()
    results: dict[str, str] = {}
    for day in days:
        key = day.isoformat()
        started = datetime.now(UTC)
        if not force and day < today - timedelta(days=1) and load_raw.last_ok(conn, "api_listing", key):
            results[key] = "ya cargado"
            continue
        try:
            codes = [row["CodigoExterno"] for row in client.listing(day)]
            done = set() if force else load_raw.fetched_after(conn, codes, day)
            pending = [c for c in codes if c not in done]
            log.info("%s: %d listadas, %d ya descargadas", key, len(codes), len(done))
            n, batch = 0, []
            for code in pending:
                detail = client.detail(code)
                if detail is not None:
                    batch.append(detail)
                if len(batch) >= batch_size:
                    n += load_raw.upsert_api_details(conn, batch)
                    batch = []
            n += load_raw.upsert_api_details(conn, batch)
            load_raw.log_extraction(conn, "api_listing", key, "ok", rows=n, started_at=started)
            results[key] = f"{n} licitaciones descargadas, {len(done)} ya estaban"
        except ApiError as exc:
            conn.rollback()
            load_raw.log_extraction(conn, "api_listing", key, "error", error=client.mask(str(exc)), started_at=started)
            results[key] = f"error: {client.mask(str(exc))}"
        log.info("%s: %s", key, results[key])
    return results


def status(conn: psycopg.Connection) -> list[tuple]:
    return conn.execute(
        """select source, count(distinct key) filter (where status = 'ok') as claves_ok,
                  count(*) filter (where status = 'error') as errores,
                  max(finished_at) as ultima
           from raw.extraction_log group by source order by source"""
    ).fetchall()
