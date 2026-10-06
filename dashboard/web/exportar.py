"""Exporta el snapshot a archivos compactos para la versión web del dashboard.

El dashboard web (dashboard/web/index.html) calcula las métricas en el navegador, así
que necesita los datos por licitación, no agregados. Para que pesen poco van como
columnas binarias (typed arrays) y catálogos JSON:

    lic.bin         una fila por licitación (columnas descritas en meta.json)
    adj.bin         una fila por licitación × proveedor adjudicado en CLP
    catalogos.json  tipos, regiones, sectores, organismos, estados, proveedores, rubros
    rubros.b64.txt  rubro (nivel 2) → licitaciones con alguna línea en ese rubro (CSR, uint32)
    nombres_todos.gz.b64.txt  nombre de todas las licitaciones, gzip (pestaña Explorar)
    codigos.txt     CodigoExterno de cada licitación, en el orden de lic.bin (carga diferida)
    nombres.json    nombre de las licitaciones con puntaje de riesgo ≥ 20 (carga diferida)
    pares.json      pares "acompañante" de proveedores (fct_par_proveedores)
    meta.json       layout de los binarios, fecha de corte y constantes
    compras.json    Compras Ágiles y tratos directos (copia de data/compras/compras.json)
    vivo.json       licitaciones en curso (copia de data/vivo/vivo.json, ver observatorio.vivo)

Las reglas son las de observatorio.metricas: los números deben coincidir con el
dashboard Streamlit y con docs/fase3_respuestas.md (lo verifica web/verificar.mjs).

Uso: uv run --group dashboard python dashboard/web/exportar.py [salida]
"""

from __future__ import annotations

import base64
import gzip
import hashlib
import io
import json
import shutil
import sys
import tarfile
from pathlib import Path

import duckdb
import httpx
import numpy as np

from observatorio.metricas import (
    DIAS_MADUREZ,
    RAZON_PRECIO_UNITARIO,
    RAZON_SOBRE_ESTIMADO,
    RIESGO_ALTO,
    RIESGO_MEDIO,
    SENALES,
    Filtros,
    Observatorio,
)

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
# Chart.js se publica junto a la página (no desde un CDN), verificado contra la integridad de npm.
CHARTJS_TGZ = "https://registry.npmjs.org/chart.js/-/chart.js-4.4.1.tgz"
CHARTJS_SHA512 = "C74QN1bxwV1v2PEujhmKjOZ7iUM4w6BWs23Md/6aOZZSlwMzeCIDGuZay++rBgChYru7/+QFeoQW0fQoP534Dg=="
SNAP = ROOT / "data" / "snapshot"
# Rubros con menos licitaciones se descartan (valores dañados en origen).
MIN_RUBRO = 30
# Bits de la columna `extra`, en orden.
EXTRA = ["x_ofertas_identicas", "x_fraccionamiento"]
ESTADOS = ["Adjudicada", "Desierta", "Revocada", "Cerrada", "Suspendida", "Publicada"]


def chartjs(target: Path) -> None:
    if target.exists():
        return
    data = httpx.get(CHARTJS_TGZ, timeout=60, follow_redirects=True).content
    if base64.b64encode(hashlib.sha512(data).digest()).decode() != CHARTJS_SHA512:
        raise SystemExit("chart.js: la integridad del paquete no coincide con npm")
    with tarfile.open(fileobj=io.BytesIO(data)) as tar:
        target.write_bytes(tar.extractfile("package/dist/chart.umd.js").read())


def catalogo(values) -> tuple[list[str], dict]:
    items = sorted({v for v in values if isinstance(v, str)})  # NaN/None = sin dato
    return items, {v: i + 1 for i, v in enumerate(items)}  # 0 = sin dato


def main(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    db = duckdb.connect()
    for name in ("licitaciones", "adjudicaciones", "proveedores", "pares", "rubros"):
        db.execute(f"create view {name} as select * from read_parquet('{SNAP / (name + '.parquet')}')")
    corte = db.execute("select max(fecha_publicacion) from licitaciones").fetchone()[0]
    lic = db.execute(
        f"""
        select *, fecha_cierre <= date '{corte}' - interval {DIAS_MADUREZ} day as madura
        from licitaciones order by codigo_externo
        """
    ).df()
    n = len(lic)

    tipos = (
        lic.groupby("tipo", dropna=False)
        .agg(d=("tipo_descripcion", "first"), o=("tipo_orden", "min"))
        .reset_index()
        .sort_values(["o", "tipo"])
    )
    tipo_items = tipos["tipo"].fillna("?").tolist()
    tipo_idx = {t: i for i, t in enumerate(tipo_items)}
    regiones, reg_idx = catalogo(lic["region_unidad"])
    sectores, sec_idx = catalogo(lic["sector"])
    orgs = lic.groupby("codigo_organismo")["nombre_organismo"].last()
    org_codes = orgs.index.tolist()
    org_idx = {c: i for i, c in enumerate(org_codes)}

    mes0 = np.datetime64("2024-01", "M")
    mes = (lic["mes_publicacion"].values.astype("datetime64[M]") - mes0).astype(np.int16)

    def i16(col):
        v = lic[col].to_numpy(dtype="float64", na_value=np.nan)
        return np.where(np.isnan(v), -32768, np.clip(v, -32767, 32767)).astype(np.int16)

    razon = lic["razon_adjudicado_estimado"].to_numpy(dtype="float64", na_value=np.nan)
    adjudicada = (lic["estado_grupo"] == "Adjudicada").to_numpy()
    ofer = lic["n_proveedores_oferentes"].fillna(0).clip(upper=255).astype(np.uint8).to_numpy()
    dofer = lic["dias_publicacion_cierre"].to_numpy(dtype="float64", na_value=np.nan)
    del dofer
    # Señales de riesgo (dbt, int_licitacion_senales) como bits, en el orden de SENALES.
    senal = np.zeros(len(lic), dtype=np.uint8)
    for bit, (col, _, _) in enumerate(SENALES):
        senal |= (lic[col].fillna(False).to_numpy(dtype=bool) & adjudicada).astype(np.uint8) << bit
    monto_clp = np.where(
        (lic["moneda_adjudicada"] == "CLP").to_numpy(),
        lic["monto_adjudicado"].to_numpy(dtype="float64", na_value=np.nan),
        np.nan,
    )

    # Rubros (nivel 2) con al menos MIN_RUBRO licitaciones: los demás son casi siempre valores
    # dañados en origen (p. ej. "EQdoPOS, PLATAFORMAS…" en el archivo de marzo de 2026).
    rub = db.execute(
        f"""
        select rubro1, rubro2, count(distinct codigo_externo) as n from rubros
        group by 1, 2 having count(distinct codigo_externo) >= {MIN_RUBRO} order by 1, 2
        """
    ).fetchall()
    rubros1 = sorted({r1 for r1, _, _ in rub})
    r1_idx = {r: i for i, r in enumerate(rubros1)}
    rubros2 = [[r1_idx[r1], r2, int(k)] for r1, r2, k in rub]
    r2_idx = {(r1, r2): i + 1 for i, (r1, r2, _) in enumerate(rub)}  # 0 = sin rubro
    principal = [r2_idx.get((a, b), 0) for a, b in zip(lic["rubro1_principal"], lic["rubro2_principal"], strict=True)]
    # Señales complementarias (int_licitacion_senales_extra), no suman al puntaje.
    extra = np.zeros(len(lic), dtype=np.uint8)
    for bit, col in enumerate(EXTRA):
        extra |= lic[col].fillna(False).to_numpy(dtype=bool).astype(np.uint8) << bit
    estimado_clp = np.where(
        (lic["moneda"] == "CLP").to_numpy(), lic["monto_estimado"].to_numpy(dtype="float64", na_value=np.nan), np.nan
    )

    columnas = {
        "mes": mes.astype(np.uint8),
        "tipo": lic["tipo"].fillna("?").map(tipo_idx).to_numpy(np.uint8),
        "region": lic["region_unidad"].map(reg_idx).fillna(0).to_numpy(np.uint8),
        "sector": lic["sector"].map(sec_idx).fillna(0).to_numpy(np.uint8),
        "org": lic["codigo_organismo"].map(org_idx).to_numpy(np.uint16),
        "estado": lic["estado_grupo"].map({e: i for i, e in enumerate(ESTADOS)}).fillna(5).to_numpy(np.uint8),
        "ofer": ofer,
        "senal": senal,
        "puntaje": lic["puntaje_riesgo"].fillna(0).to_numpy(np.uint8),
        "madura": lic["madura"].fillna(False).to_numpy(np.uint8),
        "dofer": i16("dias_publicacion_cierre"),
        "dadj": i16("dias_cierre_adjudicacion"),
        # float64: en float32, razones apenas sobre 1 (1,0000001) se redondean a 1,0 y
        # cambian "% sobre lo estimado".
        "razon": razon.astype(np.float64),
        "monto": monto_clp.astype(np.float32),
        "extra": extra,
        "rubro": np.array(principal, dtype=np.uint16),
        "estim": estimado_clp.astype(np.float32),
    }
    layout, offset = [], 0
    with (out / "lic.bin").open("wb") as fh:
        for name, arr in columnas.items():
            # Alineación a 8 bytes para poder crear Float64Array/Int16Array sin copiar.
            pad = (-offset) % 8
            fh.write(b"\0" * pad)
            offset += pad
            fh.write(arr.tobytes())
            layout.append({"col": name, "dtype": str(arr.dtype), "offset": offset})
            offset += arr.nbytes

    # Adjudicaciones en CLP con monto > 0 (base de la pregunta 3).
    codigo_idx = {c: i for i, c in enumerate(lic["codigo_externo"])}

    # Rubro → licitaciones (formato CSR: offsets[k]..offsets[k+1] en `lics`), para filtrar por
    # cualquier rubro de la licitación y no solo el principal.
    pares_rubro = db.execute("select distinct codigo_externo, rubro1, rubro2 from rubros").fetchall()
    por_rubro: list[list[int]] = [[] for _ in range(len(rubros2) + 1)]
    for c, a, b in pares_rubro:
        k = r2_idx.get((a, b))
        if k and c in codigo_idx:
            por_rubro[k].append(codigo_idx[c])
    por_rubro = [sorted(set(v)) for v in por_rubro]
    offsets = np.cumsum([0] + [len(v) for v in por_rubro]).astype(np.uint32)
    lics_rubro = np.array([i for v in por_rubro for i in v], dtype=np.uint32)
    (out / "rubros.b64.txt").write_bytes(base64.b64encode(offsets.tobytes() + lics_rubro.tobytes()))
    adj = db.execute(
        "select codigo_externo, codigo_proveedor, monto_adjudicado from adjudicaciones "
        "where moneda = 'CLP' and monto_adjudicado > 0"
    ).df()
    provs = sorted(adj["codigo_proveedor"].unique())
    prov_idx = {p: i for i, p in enumerate(provs)}
    a_lic = adj["codigo_externo"].map(codigo_idx).to_numpy(np.uint32)
    a_prov = adj["codigo_proveedor"].map(prov_idx).to_numpy(np.uint32)
    a_monto = adj["monto_adjudicado"].to_numpy(np.float64).astype(np.float32)
    with (out / "adj.bin").open("wb") as fh:
        fh.write(a_lic.tobytes())
        fh.write(a_prov.tobytes())
        fh.write(a_monto.tobytes())
    nombres = db.execute(
        "select codigo_proveedor, nombre_proveedor, rut_proveedor, n_licitaciones_ofertadas from proveedores"
    ).df()
    nombres = nombres.set_index("codigo_proveedor")
    proveedores = [
        [
            str(nombres["nombre_proveedor"].get(p) or p),
            str(nombres["rut_proveedor"].get(p) or ""),
            int(nombres["n_licitaciones_ofertadas"].get(p) or 0),
            p,  # CodigoProveedor: cruza a los oferentes de licitaciones en curso con su historial
        ]
        for p in provs
    ]
    pares = [
        [prov_idx[g], str(nombres["nombre_proveedor"].get(a) or a), int(j), int(w), a]
        for g, a, j, w in db.execute("select ganador, acompanante, juntos, gana_ganador from pares").fetchall()
        if g in prov_idx
    ]

    # Textos de carga diferida: códigos de todas las licitaciones y nombres de las que tienen señales
    # relevantes (puntaje ≥ RIESGO_MEDIO). El enlace a la ficha se deriva del código.
    (out / "codigos.txt").write_text("\n".join(lic["codigo_externo"]))
    # Nombres de todas las licitaciones (pestaña Explorar), comprimidos: ~19 MB de texto.
    todos = "\n".join((x or "").replace("\n", " ").replace("\r", " ") for x in lic["nombre"])
    (out / "nombres_todos.gz.b64.txt").write_bytes(base64.b64encode(gzip.compress(todos.encode(), 9)))
    con_nombre = lic.index[lic["puntaje_riesgo"].fillna(0).to_numpy() >= RIESGO_MEDIO]
    nombres_lic = [[int(i), lic.at[i, "nombre"]] for i in con_nombre]

    (out / "catalogos.json").write_text(
        json.dumps(
            {
                "tipos": [[t, d or "Otro"] for t, d in zip(tipo_items, tipos["d"], strict=True)],
                "regiones": regiones,
                "sectores": sectores,
                "organismos": [[c, orgs[c]] for c in org_codes],
                "estados": ESTADOS,
                "proveedores": proveedores,
                "rubros1": rubros1,
                "rubros2": rubros2,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
    )
    # allow_nan=False: un NaN en el JSON rompe JSON.parse en el navegador.
    for name, obj in (("nombres", nombres_lic), ("pares", pares)):
        (out / f"{name}.json").write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":"), allow_nan=False))
    snap_meta = json.loads((SNAP / "meta.json").read_text())
    (out / "meta.json").write_text(
        json.dumps(
            {
                "n": n,
                "n_adj": len(adj),
                "layout": layout,
                "mes0": "2024-01",
                "corte": str(corte),
                "corte_datos": snap_meta.get("corte_datos"),
                "generado": snap_meta.get("generado"),
                "constantes": {
                    "DIAS_MADUREZ": DIAS_MADUREZ,
                    "RAZON_SOBRE_ESTIMADO": RAZON_SOBRE_ESTIMADO,
                    "RAZON_PRECIO_UNITARIO": RAZON_PRECIO_UNITARIO,
                    "MIN_GRUPO": 30,
                    "RIESGO_ALTO": RIESGO_ALTO,
                    "RIESGO_MEDIO": RIESGO_MEDIO,
                    "SENALES": [[c, e, w] for c, e, w in SENALES],
                    "EXTRA": EXTRA,
                    # Tope de cada tipo (UTM) para la pestaña En curso, con el régimen vigente: desde
                    # noviembre de 2025 no se publican LQ ni H2 y LP / B2 cubren hasta 5.000 UTM.
                    "UTM_CLP": 70000,
                    "TOPES_UTM": {
                        "L1": 100,
                        "E2": 100,
                        "LE": 1000,
                        "CO": 1000,
                        "LP": 5000,
                        "B2": 5000,
                        "LQ": 5000,
                        "H2": 5000,
                    },
                },
            },
            indent=1,
        )
    )
    # Página: cifras sin filtro incrustadas (primera vista completa) + scripts.
    obs = Observatorio(SNAP)
    f0 = Filtros()
    r = obs.resumen(f0)
    k = obs.concentracion_kpis(f0)
    init = {
        "resumen": {
            **{c: float(r[c]) for c in ("n", "adjudicadas", "monto_clp", "organismos")},
            "proveedores": len(provs),
        },
        "competencia": obs.competencia_kpis(f0),
        "precio": obs.precio_kpis(f0),
        "concentracion": {"kpis": k},
        "proceso": obs.proceso_kpis(f0),
    }
    html = (HERE / "index.html").read_text()
    assert "/*INIT*/null" in html
    (out / "index.html").write_text(html.replace("/*INIT*/null", json.dumps(init, default=float)))
    shutil.copy(HERE / "metricas.js", out / "metricas.js")
    chartjs(out / "chart.umd.js")
    # La plataforma de artifacts no sirve binarios genéricos: los binarios van también en
    # base64 como .txt (la página los decodifica). Los .bin quedan para verificar.py.
    for name in ("lic", "adj"):
        (out / f"{name}.b64.txt").write_bytes(base64.b64encode((out / f"{name}.bin").read_bytes()))
    # Compras Ágiles y tratos directos (observatorio compras), si existe.
    compras = ROOT / "data" / "compras" / "compras.json"
    if compras.exists():
        shutil.copy(compras, out / "compras.json")
    else:
        print("aviso: falta data/compras/compras.json (make compras); la pestaña Compras directas no tendrá datos")
    # Licitaciones en curso (observatorio vivo): se publica la última generada, si existe.
    vivo = ROOT / "data" / "vivo" / "vivo.json"
    if vivo.exists():
        shutil.copy(vivo, out / "vivo.json")
    else:
        print("aviso: falta data/vivo/vivo.json (make vivo); la pestaña En curso no tendrá datos")
    for f in sorted(out.iterdir()):
        print(f"{f.name}: {f.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data" / "web")
