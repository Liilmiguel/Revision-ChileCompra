"""Exporta los marts a Parquet (data/snapshot/) para el dashboard y el análisis.

El dashboard no consulta PostgreSQL: lee una foto inmutable, así se puede publicar
sin exponer la base y los números del análisis escrito coinciden con los del tablero.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import psycopg

QUERIES = {
    "licitaciones": """
        select codigo_externo, nombre, tipo, tipo_descripcion, tipo_orden,
               codigo_organismo, nombre_organismo, sector, region_unidad,
               codigo_estado, estado_grupo, estado_es_final, fuente_estado,
               fecha_publicacion, mes_publicacion, fecha_cierre, dias_publicacion_cierre,
               fecha_adjudicacion, dias_cierre_adjudicacion,
               moneda, monto_estimado, monto_estimado_visible,
               monto_adjudicado, monto_adjudicado_bruto, moneda_adjudicada, razon_adjudicado_estimado,
               numero_oferentes, n_proveedores_oferentes, n_proveedores_adjudicados,
               es_oferente_unico, n_lineas_atipicas, link
        from marts.fct_licitacion
        where fecha_publicacion >= %(desde)s
    """,
    "adjudicaciones": """
        select a.codigo_externo, a.codigo_proveedor, a.moneda, a.n_lineas, a.monto_adjudicado
        from marts.fct_adjudicacion a
        join marts.fct_licitacion l using (codigo_externo)
        where l.fecha_publicacion >= %(desde)s
    """,
    "proveedores": """
        select codigo_proveedor, rut_proveedor, nombre_proveedor, razon_social_proveedor
        from marts.dim_proveedor
    """,
}


def _column(values: list) -> list:
    # pyarrow no infiere bien Decimal mezclado con None: se pasa a float.
    return [float(v) if isinstance(v, Decimal) else v for v in values]


def export(conn: psycopg.Connection, out_dir: Path, desde: str = "2024-01-01") -> dict[str, int]:
    import pyarrow as pa
    import pyarrow.parquet as pq

    out_dir.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}
    for name, sql in QUERIES.items():
        cur = conn.execute(sql, {"desde": desde})
        cols = [d.name for d in cur.description]
        rows = cur.fetchall()
        data = {c: _column([r[i] for r in rows]) for i, c in enumerate(cols)}
        pq.write_table(pa.table(data), out_dir / f"{name}.parquet", compression="zstd")
        counts[name] = len(rows)
    corte = conn.execute(
        "select max(finished_at) from raw.extraction_log where status = 'ok' and source = 'bulk'"
    ).fetchone()[0]
    meta = {
        "generado": datetime.now(UTC).isoformat(timespec="seconds"),
        "corte_datos": corte.isoformat(timespec="seconds") if corte else None,
        "desde": desde,
        "filas": counts,
    }
    (out_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2))
    return counts
