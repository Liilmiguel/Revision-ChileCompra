"""Compara las métricas de dashboard/web/metricas.js con observatorio.metricas.

Uso: uv run --group dashboard python dashboard/web/verificar.py   (requiere node)
"""

from __future__ import annotations

import json
import math
import subprocess
import sys
from datetime import date
from pathlib import Path

from observatorio.metricas import Filtros, Observatorio

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "data" / "web"

NODE = r"""
const fs = require("fs");
const M = require(process.argv[1] + "/metricas.js");
const dir = process.argv[2];
const meta = JSON.parse(fs.readFileSync(dir + "/meta.json"));
const cat = JSON.parse(fs.readFileSync(dir + "/catalogos.json"));
const buf = (f) => {
  const b = fs.readFileSync(dir + "/" + f);
  return b.buffer.slice(b.byteOffset, b.byteOffset + b.length);
};
const d = M.cargar(meta, buf("lic.bin"), buf("adj.bin"), cat);
const casos = JSON.parse(process.argv[3]);
const out = casos.map((f) => {
  const mk = M.mascara(d, f);
  const r = M.resumen(d, mk), c = M.competencia(d, mk, 33), p = M.precio(d, mk);
  const k = M.concentracion(d, mk, cat.proveedores), pr = M.proceso(d, mk, 33), a = M.alertasResumen(d, mk);
  return { n: r.n, adjudicadas: r.adjudicadas, monto_clp: r.monto_clp, organismos: r.organismos,
    pct_unico: c.pct_unico, mediana_oferentes: c.mediana_oferentes, n_comp: c.n,
    precio_n: p.n, precio_mediana: p.mediana, pct_sobre: p.pct_sobre, pct_precio_unitario: p.pct_precio_unitario,
    comp_mediana_1: p.comp.length ? p.comp[0].mediana : null,
    conc_n: k.kpis.n, pct_alta: k.kpis.pct_alta ?? null, mediana_share_top: k.kpis.mediana_share_top ?? null,
    share_top10: k.mercado.share_top10, top1: k.orgs.length ? k.orgs[0].proveedor_top : null,
    proc_n: pr.n, pct_desierta: pr.pct_desierta, dias_adj: pr.mediana_dias_adjudicar, dias_of: pr.mediana_dias_oferta,
    alertas_2: a[2], alertas_3: a[3] };
});
console.log(JSON.stringify(out));
"""


def python(obs: Observatorio, f: Filtros) -> dict:
    r, c, p = obs.resumen(f), obs.competencia_kpis(f), obs.precio_kpis(f)
    pc = obs.precio_vs_competencia(f)
    k, mk, pr = obs.concentracion_kpis(f), obs.concentracion_mercado(f), obs.proceso_kpis(f)
    orgs = obs.concentracion_organismos(f)
    al = obs.alertas_resumen(f).set_index("senales")["n"]
    return {
        "n": r["n"],
        "adjudicadas": r["adjudicadas"],
        "monto_clp": r["monto_clp"],
        "organismos": r["organismos"],
        "pct_unico": c["pct_unico"],
        "mediana_oferentes": c["mediana_oferentes"],
        "n_comp": c["n"],
        "precio_n": p["n"],
        "precio_mediana": p["mediana"],
        "pct_sobre": p["pct_sobre"],
        "pct_precio_unitario": p["pct_precio_unitario"],
        "comp_mediana_1": float(pc["mediana"].iloc[0]) if len(pc) else None,
        "conc_n": k["n"],
        "pct_alta": k.get("pct_alta"),
        "mediana_share_top": k.get("mediana_share_top"),
        "share_top10": mk["share_top10"],
        "top1": orgs["proveedor_top"].iloc[0] if len(orgs) else None,
        "proc_n": pr["n"],
        "pct_desierta": pr["pct_desierta"],
        "dias_adj": pr["mediana_dias_adjudicar"],
        "dias_of": pr["mediana_dias_oferta"],
        "alertas_2": int(al.get(2, 0)),
        "alertas_3": int(al.get(3, 0)),
    }


def igual(a, b) -> bool:
    if a is None or b is None or (isinstance(a, float) and math.isnan(a)):
        return (a is None or (isinstance(a, float) and math.isnan(a))) and (
            b is None or (isinstance(b, float) and math.isnan(b))
        )
    if isinstance(a, str) or isinstance(b, str):
        return a == b
    return math.isclose(float(a), float(b), rel_tol=1e-4, abs_tol=1e-9)


def main() -> None:
    obs = Observatorio(ROOT / "data" / "snapshot")
    meta = json.loads((WEB / "meta.json").read_text())
    cat = json.loads((WEB / "catalogos.json").read_text())
    org_idx = {c: i for i, (c, _) in enumerate(cat["organismos"])}
    tipo_idx = {t: i for i, (t, _) in enumerate(cat["tipos"])}
    reg_idx = {r: i + 1 for i, r in enumerate(cat["regiones"])}
    top_org = obs.opciones()["organismos"].iloc[0]["c"]
    casos = [
        (Filtros(), {"desde": 0, "hasta": 32}),
        (
            Filtros(desde=date(2025, 1, 1), hasta=date(2025, 12, 31), tipos=["LE"]),
            {"desde": 12, "hasta": 23, "tipo": tipo_idx["LE"]},
        ),
        (Filtros(organismos=[top_org]), {"desde": 0, "hasta": 32, "org": org_idx[top_org]}),
        (
            Filtros(regiones=["Región de Valparaíso "]),
            {"desde": 0, "hasta": 32, "region": reg_idx["Región de Valparaíso "]},
        ),
    ]
    js = json.loads(
        subprocess.run(
            ["node", "-e", NODE, str(Path(__file__).parent), str(WEB), json.dumps([c[1] for c in casos])],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    )
    fallas = 0
    for (f, _), j in zip(casos, js, strict=True):
        py = python(obs, f)
        for key, v in py.items():
            if not igual(v, j[key]):
                fallas += 1
                print(f"DIFERENCIA {f} {key}: python={v} js={j[key]}")
    print(f"{len(casos)} casos, {len(casos) * len(js[0])} métricas, {fallas} diferencias (meta n={meta['n']})")
    sys.exit(1 if fallas else 0)


if __name__ == "__main__":
    main()
