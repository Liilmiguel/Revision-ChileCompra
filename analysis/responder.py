"""Fase 3: responde las 4 preguntas sobre el snapshot y escribe docs/fase3_respuestas.md.

Usa las mismas métricas que el dashboard (observatorio.metricas).
Uso: uv run --group dashboard python analysis/responder.py
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from observatorio.metricas import DIAS_MADUREZ, MIN_GRUPO, RIESGO_ALTO, SENALES, Filtros, Observatorio

ROOT = Path(__file__).resolve().parents[1]


def pct(x: float, dec: int = 1) -> str:
    return f"{100 * x:.{dec}f} %".replace(".", ",")


def n(x: float, dec: int = 0) -> str:
    return f"{x:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def clp(x: float) -> str:
    return f"$ {n(x / 1e9, 1)} mil millones" if x >= 1e9 else f"$ {n(x / 1e6, 1)} millones"


def md(df: pd.DataFrame, formatos: dict[str, callable]) -> str:
    df = df.copy()
    for col, fmt in formatos.items():
        df[col] = df[col].map(lambda v, fmt=fmt: "—" if pd.isna(v) else fmt(v))
    head = "| " + " | ".join(df.columns) + " |\n|" + "---|" * len(df.columns) + "\n"
    return head + "\n".join("| " + " | ".join(str(v) for v in row) + " |" for row in df.itertuples(index=False))


def main() -> None:
    obs = Observatorio(ROOT / "data" / "snapshot")
    f = Filtros()
    r = obs.resumen(f)
    ck, pk, kk, mk, pr = (
        obs.competencia_kpis(f),
        obs.precio_kpis(f),
        obs.concentracion_kpis(f),
        obs.concentracion_mercado(f),
        obs.proceso_kpis(f),
    )
    pc = obs.precio_vs_competencia(f)
    comp_tipo = obs.competencia_por(f, "tipo_descripcion")
    prec_tipo = obs.precio_por_tipo(f)
    proc_tipo = obs.proceso_por_tipo(f)
    orgs = obs.concentracion_organismos(f)
    alert = obs.alertas_resumen(f)
    prov = obs.proveedores_riesgo(f)
    orgs_r = obs.organismos_riesgo(f)
    pares = obs.q("select * from pares")
    meses = obs.opciones()["meses"].iloc[0]
    mensual = obs.mensual(f)
    antes = mensual.loc[mensual["mes"] < pd.Timestamp("2024-12-01"), "publicadas"].mean()
    despues = mensual.loc[mensual["mes"] >= pd.Timestamp("2025-01-01"), "publicadas"].mean()

    out = [
        "# Fase 3: respuestas",
        "",
        f"Generado por `analysis/responder.py` sobre el snapshot del {obs.meta['generado'][:10]} "
        f"(licitaciones publicadas entre {meses['desde']:%Y-%m} y {meses['hasta']:%Y-%m}). "
        "Definiciones y limitaciones en `docs/fase3_preguntas.md`; los mismos números se ven y "
        "filtran en el dashboard (`make dashboard`).",
        "",
        f"Universo: {n(r['n'])} licitaciones, {n(r['adjudicadas'])} adjudicadas, "
        f"{n(r['organismos'])} organismos, {n(r['proveedores'])} proveedores adjudicados, "
        f"$ {n(r['monto_clp'] / 1e9)} mil millones adjudicados en CLP.",
        "",
        "**Quiebre en diciembre de 2024**: las licitaciones publicadas por mes caen de "
        f"{n(antes)} (promedio enero–noviembre 2024) a {n(despues)} (promedio desde enero 2025). "
        "[Probable] Coincide con la entrada en vigencia de la Ley 21.634, que modernizó las compras "
        "públicas; comparar niveles antes y después de esa fecha mezcla dos regímenes.",
        "",
        "## 1. Competencia: ¿cuántas empresas compiten por cada licitación?",
        "",
        f"**{pct(ck['pct_unico'])} de las {n(ck['n'])} licitaciones adjudicadas tuvo un solo oferente.** "
        f"La mediana es {n(ck['mediana_oferentes'])} oferentes (promedio {n(ck['media_oferentes'], 1)}).",
        "",
        md(
            comp_tipo.rename(
                columns={"grupo": "tipo", "pct_unico": "% oferente único", "mediana_oferentes": "mediana"}
            ),
            {"% oferente único": pct, "n": n, "mediana": n},
        ),
        "",
        "## 2. Precio: ¿se adjudica por sobre o bajo lo estimado?",
        "",
        f"**La mediana adjudica {pct(pk['mediana'], 0)} del monto estimado** ({n(pk['n'])} licitaciones). "
        f"{pct(pk['pct_sobre'])} supera lo estimado y {pct(pk['pct_sobre_20'])} lo supera en más de 20 %. "
        f"Se excluye el {pct(pk['pct_precio_unitario'])} de las adjudicadas con razón bajo 10 %: casi siempre "
        "convenios de suministro adjudicados por precio unitario, donde la razón no mide precio. "
        "La competencia baja el precio relativo:",
        "",
        md(
            pc.rename(columns={"oferentes": "oferentes (10 = 10+)"}),
            {"mediana": lambda v: pct(v, 0), "p25": lambda v: pct(v, 0), "p75": lambda v: pct(v, 0), "n": n},
        ),
        "",
        md(
            prec_tipo.drop(columns="orden").rename(columns={"grupo": "tipo", "pct_sobre": "% sobre estimado"}),
            {"mediana": lambda v: pct(v, 0), "% sobre estimado": pct, "n": n},
        ),
        "",
        "## 3. Concentración: ¿cuán concentradas están las compras?",
        "",
        f"A nivel país el mercado está repartido: los 10 mayores proveedores suman {pct(mk['share_top10'])} "
        f"del monto en CLP entre {n(mk['proveedores'])} proveedores. **Dentro de cada organismo no**: "
        f"{pct(kk['pct_alta'], 0)} de los {n(kk['n'])} organismos con al menos {MIN_GRUPO} licitaciones "
        f"adjudicadas tiene HHI > 2.500, y en la mediana su principal proveedor se lleva "
        f"{pct(kk['mediana_share_top'], 0)} del monto.",
        "",
        "Organismos más concentrados (con al menos 30 licitaciones):",
        "",
        md(
            orgs.head(15)[["nombre_organismo", "hhi", "share_top", "proveedor_top", "n_lic"]].rename(
                columns={
                    "nombre_organismo": "organismo",
                    "share_top": "principal",
                    "proveedor_top": "proveedor principal",
                    "n_lic": "licitaciones",
                }
            ),
            {"hhi": n, "principal": lambda v: pct(v, 0), "licitaciones": n},
        ),
        "",
        "## 4. Proceso: ¿cuántas fracasan y cuánto demoran?",
        "",
        f"De {n(pr['n'])} licitaciones cerradas hace más de {DIAS_MADUREZ} días, "
        f"**{pct(pr['pct_desierta'])} quedó desierta** y {pct(pr['pct_revocada'])} fue revocada; "
        f"{pct(pr['pct_adjudicada'])} se adjudicó y {pct(pr['pct_sin_resolver'])} sigue sin resolución en los "
        f"datos. Recepción de ofertas: mediana {n(pr['mediana_dias_oferta'])} días; del cierre a la "
        f"adjudicación: {n(pr['mediana_dias_adjudicar'])} días.",
        "",
        md(
            proc_tipo.drop(columns="orden").rename(columns={"grupo": "tipo"}),
            {
                "n": n,
                "adjudicada": pct,
                "desierta": pct,
                "revocada": pct,
                "sin_resolver": pct,
                "dias_oferta": n,
                "dias_adjudicar": n,
            },
        ),
        "",
        "## Señales de alerta",
        "",
        "Cada licitación adjudicada suma un puntaje de 0 a 100 con seis señales ponderadas "
        f"(definiciones en `docs/fase3_preguntas.md`). **{n(alert['alto'])} licitaciones tienen riesgo alto** "
        f"(puntaje ≥ {RIESGO_ALTO}, {pct(alert['alto'] / alert['n'], 2)} de las adjudicadas) y suman "
        f"$ {n(alert['monto_alto'] / 1e9)} mil millones; {n(alert['medio'])} tienen riesgo medio, casi todas solo "
        "por oferente único.",
        "",
        md(
            pd.DataFrame([{"señal": e, "peso": w, "% de las adjudicadas": alert[c]} for c, e, w in SENALES]),
            {"% de las adjudicadas": pct},
        ),
        "",
        "### Proveedores con más monto en licitaciones de riesgo alto",
        "",
        "Dependencia: parte de sus ingresos que viene de su organismo principal. Captura: parte del gasto de ese "
        "organismo que se lleva. Una fila aquí no implica irregularidad del proveedor: las señales describen "
        "cómo se hizo la licitación.",
        "",
        md(
            prov.head(15)[
                [
                    "proveedor",
                    "n_lic",
                    "n_alto",
                    "monto_alto",
                    "pct_unico",
                    "organismo_principal",
                    "dependencia",
                    "captura",
                    "n_acompanantes",
                ]
            ].rename(
                columns={
                    "n_lic": "ganadas",
                    "n_alto": "riesgo alto",
                    "monto_alto": "monto riesgo alto",
                    "pct_unico": "% único",
                    "organismo_principal": "organismo principal",
                    "n_acompanantes": "acompañantes",
                }
            ),
            {
                "monto riesgo alto": clp,
                "% único": lambda v: pct(v, 0),
                "dependencia": lambda v: pct(v, 0),
                "captura": lambda v: pct(v, 0),
            },
        ),
        "",
        "### Organismos con mayor proporción de riesgo alto",
        "",
        md(
            orgs_r.head(10)[["organismo", "n", "pct_alto", "pct_unico", "pct_descalificada"]].rename(
                columns={
                    "n": "adjudicadas",
                    "pct_alto": "% riesgo alto",
                    "pct_unico": "% único",
                    "pct_descalificada": "% descalificada",
                }
            ),
            {"adjudicadas": n, "% riesgo alto": pct, "% único": pct, "% descalificada": pct},
        ),
        "",
        f'Pares "acompañante" (ofertan juntos 5+ veces en licitaciones de 2 a 4 oferentes, uno gana 80 %+ y el '
        f"otro nunca): {n(len(pares))}. Pueden ser competencia simulada o mercados de nicho con pocos actores.",
        "",
    ]
    path = ROOT / "docs" / "fase3_respuestas.md"
    path.write_text("\n".join(out))
    print(f"escrito {path}")


if __name__ == "__main__":
    main()
