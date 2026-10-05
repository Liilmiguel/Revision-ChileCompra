"""Escritura en el schema raw de PostgreSQL y bitácora de extracciones."""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from datetime import UTC, datetime

import psycopg
from psycopg.types.json import Jsonb

from observatorio.config import ROOT

SQL_INIT = ROOT / "sql" / "init"


def connect(url: str) -> psycopg.Connection:
    return psycopg.connect(url)


def init_db(conn: psycopg.Connection) -> None:
    for path in sorted(SQL_INIT.glob("*.sql")):
        conn.execute(path.read_text())
    conn.commit()


def _clean(value: str | None) -> str | None:
    # jsonb no admite el carácter NUL.
    return value.replace("\x00", "") if value else value


def log_extraction(
    conn: psycopg.Connection,
    source: str,
    key: str,
    status: str,
    *,
    rows: int | None = None,
    remote_version: str | None = None,
    error: str | None = None,
    started_at: datetime | None = None,
) -> None:
    conn.execute(
        """insert into raw.extraction_log (source, key, status, rows, remote_version, error, started_at, finished_at)
           values (%s, %s, %s, %s, %s, %s, coalesce(%s, now()), now())""",
        (source, key, status, rows, remote_version, error, started_at),
    )
    conn.commit()


def last_ok(conn: psycopg.Connection, source: str, key: str) -> tuple[datetime, str | None] | None:
    """(finished_at, remote_version) de la última extracción exitosa, o None."""
    return conn.execute(
        """select finished_at, remote_version from raw.extraction_log
           where source = %s and key = %s and status = 'ok'
           order by finished_at desc limit 1""",
        (source, key),
    ).fetchone()


def split_rows(
    rows: Iterable[dict[str, str | None]],
) -> tuple[dict[str, dict[str, str | None]], Iterator[tuple[int, str, dict[str, str | None]]]]:
    """Separa las filas del CSV en (primera fila por CodigoExterno, diferencias por fila).

    Devuelve el dict de cabeceras (se completa a medida que se consume el iterador)
    y un iterador de (row_num, codigo_externo, columnas que difieren de la cabecera)."""
    heads: dict[str, dict[str, str | None]] = {}

    def lines() -> Iterator[tuple[int, str, dict[str, str | None]]]:
        for n, row in enumerate(rows, start=1):
            row = {k: _clean(v) for k, v in row.items()}
            code = row["CodigoExterno"]
            head = heads.setdefault(code, row)
            yield n, code, {k: v for k, v in row.items() if head.get(k) != v}

    return heads, lines()


def replace_bulk_month(conn: psycopg.Connection, month: str, rows: Iterable[dict[str, str | None]]) -> int:
    """Reemplaza el mes completo en una sola transacción. Devuelve las filas del CSV cargadas."""
    extracted_at = datetime.now(UTC)
    heads, lines = split_rows(rows)
    n = 0
    with conn.transaction():
        conn.execute("delete from raw.bulk_fila where source_month = %s", (month,))
        conn.execute("delete from raw.bulk_licitacion where source_month = %s", (month,))
        with conn.cursor().copy("copy raw.bulk_fila (source_month, row_num, codigo_externo, data) from stdin") as copy:
            for n, code, diff in lines:
                copy.write_row((month, n, code, json.dumps(diff, ensure_ascii=False)))
        with conn.cursor().copy(
            "copy raw.bulk_licitacion (source_month, codigo_externo, data, extracted_at) from stdin"
        ) as copy:
            for code, head in heads.items():
                copy.write_row((month, code, json.dumps(head, ensure_ascii=False), extracted_at))
    return n


def upsert_api_details(conn: psycopg.Connection, details: Iterable[dict]) -> int:
    extracted_at = datetime.now(UTC)
    n = 0
    with conn.transaction():
        for detail in details:
            conn.execute(
                """insert into raw.api_licitacion (codigo_externo, data, extracted_at) values (%s, %s, %s)
                   on conflict (codigo_externo)
                   do update set data = excluded.data, extracted_at = excluded.extracted_at""",
                (detail["CodigoExterno"], Jsonb(detail), extracted_at),
            )
            n += 1
    return n
