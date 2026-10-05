"""Pruebas contra PostgreSQL. Se saltan si no hay base disponible (DATABASE_URL o la del docker-compose)."""

import json
import uuid
from pathlib import Path

import psycopg
import pytest

from observatorio import config, load_raw

DETAIL = json.loads((Path(__file__).parent / "fixtures" / "api_detail.json").read_text())["Listado"][0]


@pytest.fixture
def conn():
    try:
        c = psycopg.connect(config.database_url(), connect_timeout=3)
    except psycopg.OperationalError:
        pytest.skip("PostgreSQL no disponible")
    load_raw.init_db(c)
    yield c
    c.rollback()
    c.close()


@pytest.fixture
def month():
    # Clave que no choca con meses reales cargados en la misma base.
    return f"test-{uuid.uuid4().hex[:8]}"


def _cleanup(conn, month):
    conn.execute("delete from raw.bulk_fila where source_month = %s", (month,))
    conn.execute("delete from raw.bulk_licitacion where source_month = %s", (month,))
    conn.commit()


ROWS = [
    {"CodigoExterno": "1-1-LE26", "Nombre": "A", "CodigoProveedor": "10"},
    {"CodigoExterno": "1-1-LE26", "Nombre": "A", "CodigoProveedor": "11"},
    {"CodigoExterno": "2-2-LP26", "Nombre": "B\x00", "CodigoProveedor": None},
]


def test_replace_bulk_month_es_idempotente_y_reconstruible(conn, month):
    try:
        assert load_raw.replace_bulk_month(conn, month, ROWS) == 3
        assert load_raw.replace_bulk_month(conn, month, ROWS) == 3
        got = conn.execute(
            "select data from raw.bulk_fila_completa where source_month = %s order by row_num", (month,)
        ).fetchall()
        expected = [dict(r, Nombre=r["Nombre"].replace("\x00", "")) for r in ROWS]
        assert [g[0] for g in got] == expected
        n_lic = conn.execute("select count(*) from raw.bulk_licitacion where source_month = %s", (month,)).fetchone()
        assert n_lic == (2,)
    finally:
        _cleanup(conn, month)


def test_bitacora_last_ok(conn, month):
    try:
        assert load_raw.last_ok(conn, "bulk", month) is None
        load_raw.log_extraction(conn, "bulk", month, "error", error="x")
        assert load_raw.last_ok(conn, "bulk", month) is None
        load_raw.log_extraction(conn, "bulk", month, "ok", rows=3, remote_version="v1")
        assert load_raw.last_ok(conn, "bulk", month)[1] == "v1"
    finally:
        conn.execute("delete from raw.extraction_log where key = %s", (month,))
        conn.commit()


def test_upsert_api_details(conn):
    code = f"TEST-{uuid.uuid4().hex[:8]}"
    try:
        load_raw.upsert_api_details(conn, [dict(DETAIL, CodigoExterno=code, CodigoEstado=6)])
        load_raw.upsert_api_details(conn, [dict(DETAIL, CodigoExterno=code, CodigoEstado=8)])
        row = conn.execute(
            "select data->>'CodigoEstado' from raw.api_licitacion where codigo_externo = %s", (code,)
        ).fetchall()
        assert row == [("8",)]
    finally:
        conn.execute("delete from raw.api_licitacion where codigo_externo = %s", (code,))
        conn.commit()
