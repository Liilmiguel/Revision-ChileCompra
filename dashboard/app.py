"""Observatorio de Compras Públicas: dashboard de las 4 preguntas.

Lee el snapshot Parquet (`make snapshot`), no la base de datos.
Ejecutar: `make dashboard` (o `uv run --group dashboard streamlit run dashboard/app.py`).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from observatorio.metricas import (
    DIAS_MADUREZ,
    MIN_GRUPO,
    RAZON_PRECIO_UNITARIO,
    RAZON_SOBRE_ESTIMADO,
    Filtros,
    Observatorio,
)

SOBRE_PCT = round(100 * (RAZON_SOBRE_ESTIMADO - 1))

SNAPSHOT = Path(__file__).resolve().parents[1] / "data" / "snapshot"

st.set_page_config(page_title="Observatorio de Compras Públicas", page_icon="📊", layout="wide")

# ---------------------------------------------------------------- estilo

TEMAS = {
    "light": {
        "s1": "#2a78d6",
        "s2": "#eb6834",
        "s3": "#1baf7a",
        "s4": "#eda100",
        "ink": "#0b0b0b",
        "ink2": "#52514e",
        "muted": "#898781",
        "grid": "#e1e0d9",
        "axis": "#c3c2b7",
        "neutral": "#c3c2b7",
    },
    "dark": {
        "s1": "#3987e5",
        "s2": "#d95926",
        "s3": "#199e70",
        "s4": "#c98500",
        "ink": "#ffffff",
        "ink2": "#c3c2b7",
        "muted": "#898781",
        "grid": "#2c2c2a",
        "axis": "#383835",
        "neutral": "#52514e",
    },
}
try:
    C = TEMAS["dark" if st.context.theme.type == "dark" else "light"]
except AttributeError:
    C = TEMAS["light"]

FONT = 'system-ui, -apple-system, "Segoe UI", sans-serif'

st.markdown(
    """
    <style>
      [data-testid="stMetricValue"] { font-size: 1.9rem; }
      [data-testid="stMetricLabel"] p { font-size: .85rem; }
      .respuesta { font-size: 1.05rem; line-height: 1.5; padding: .75rem 1rem; border-radius: .5rem;
                   border: 1px solid rgba(128,128,128,.25); margin: .25rem 0 1rem; }
      .nota { font-size: .8rem; opacity: .75; }
    </style>
    """,
    unsafe_allow_html=True,
)


def layout(fig: go.Figure, height: int = 340, **kw) -> go.Figure:
    fig.update_layout(
        height=height,
        margin=dict(l=8, r=8, t=64, b=8),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family=FONT, color=C["ink2"], size=13),
        title=dict(text=kw.pop("title", None), font=dict(color=C["ink"], size=15), y=0.98, yanchor="top"),
        hoverlabel=dict(font_family=FONT),
        legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="left", x=0, title_text="", traceorder="normal"),
        separators=",.",  # coma decimal y punto de miles
        bargap=0.25,
        **kw,
    )
    fig.update_xaxes(gridcolor=C["grid"], linecolor=C["axis"], zeroline=False, tickfont_color=C["muted"])
    fig.update_yaxes(gridcolor=C["grid"], linecolor=C["axis"], zeroline=False, tickfont_color=C["muted"])
    # Ejes de fecha en AAAA-MM: plotly no trae los meses en español.
    x0 = fig.data[0].x if fig.data else None
    if x0 is not None and len(x0) and (pd.Series(x0).dtype.kind == "M" or isinstance(x0[0], date)):
        fig.update_xaxes(tickformat="%Y-%m")
    return fig


def pct(x: float | None, dec: int = 1) -> str:
    # Espacio no separable: "3,2 %" no se parte entre líneas.
    return "—" if x is None or pd.isna(x) else f"{100 * x:.{dec}f}\u00a0%".replace(".", ",")


def num(x: float | None, dec: int = 0) -> str:
    if x is None or pd.isna(x):
        return "—"
    return f"{x:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def clp(x: float | None) -> str:
    if x is None or pd.isna(x):
        return "—"
    for div, suf in ((1e12, " billones"), (1e9, " mil millones"), (1e6, " millones")):
        if abs(x) >= div:
            return f"$ {num(x / div, 1)}{suf}"
    return f"$ {num(x)}"


def tabla(df: pd.DataFrame, nombre: str, **kw) -> None:
    with st.expander("Ver datos"):
        st.dataframe(df, width="stretch", hide_index=True, **kw)
        st.download_button(
            "Descargar CSV", df.to_csv(index=False).encode("utf-8"), f"{nombre}.csv", "text/csv", key=f"dl_{nombre}"
        )


def respuesta(texto: str) -> None:
    st.markdown(f'<div class="respuesta">{texto}</div>', unsafe_allow_html=True)


# ---------------------------------------------------------------- datos


@st.cache_resource
def cargar() -> Observatorio:
    return Observatorio(SNAPSHOT)


if not (SNAPSHOT / "meta.json").exists():
    st.error("No hay snapshot. Corre `make backfill`, `make dbt` y `make snapshot` antes de abrir el dashboard.")
    st.stop()

obs = cargar()
opc = obs.opciones()

# ---------------------------------------------------------------- filtros

with st.sidebar:
    st.header("Filtros")
    meses = pd.date_range(opc["meses"].iloc[0]["desde"], opc["meses"].iloc[0]["hasta"], freq="MS")
    etiquetas = [m.strftime("%Y-%m") for m in meses]
    rango = st.select_slider("Mes de publicación", options=etiquetas, value=(etiquetas[0], etiquetas[-1]))
    tipos_df = opc["tipos"]
    tipos = st.multiselect(
        "Tipo de licitación",
        tipos_df["tipo"].tolist(),
        format_func=lambda t: f"{t} · {tipos_df.set_index('tipo').loc[t, 'd'] or 'Otro'}",
        placeholder="Todos",
    )
    regiones = st.multiselect("Región", opc["regiones"]["r"].tolist(), placeholder="Todas")
    sectores = st.multiselect("Sector", opc["sectores"]["s"].tolist(), placeholder="Todos")
    org_df = opc["organismos"]
    nombres_org = dict(zip(org_df["c"], org_df["nombre"], strict=True))
    organismos = st.multiselect(
        "Organismo comprador",
        org_df["c"].tolist(),
        format_func=lambda c: nombres_org.get(c) or c,
        placeholder="Todos (escribe para buscar)",
    )
    st.divider()
    st.caption(
        f"Datos: descarga masiva de Mercado Público + API. Corte: {obs.meta.get('corte_datos', '—')[:10]}. "
        f"Snapshot generado {obs.meta['generado'][:10]}."
    )

hasta = (pd.Timestamp(rango[1]) + pd.offsets.MonthEnd(0)).date()
F = Filtros(
    desde=pd.Timestamp(rango[0]).date(),
    hasta=hasta,
    tipos=tipos,
    regiones=regiones,
    sectores=sectores,
    organismos=organismos,
)

st.title("Observatorio de Compras Públicas")
st.caption("Licitaciones de Mercado Público (ChileCompra) · competencia, precio, concentración y proceso")

tabs = st.tabs(
    ["Resumen", "1 · Competencia", "2 · Precio", "3 · Concentración", "4 · Proceso", "Señales de alerta", "Metodología"]
)

# ---------------------------------------------------------------- resumen

with tabs[0]:
    r = obs.resumen(F)
    ck, pk, kk, prk = obs.competencia_kpis(F), obs.precio_kpis(F), obs.concentracion_kpis(F), obs.proceso_kpis(F)
    c = st.columns(5)
    c[0].metric("Licitaciones publicadas", num(r["n"]))
    c[1].metric("Adjudicadas", num(r["adjudicadas"]))
    c[2].metric("Monto adjudicado (CLP)", clp(r["monto_clp"]))
    c[3].metric("Organismos compradores", num(r["organismos"]))
    c[4].metric("Proveedores adjudicados", num(r["proveedores"]))

    st.subheader("Las cuatro respuestas")
    a, b = st.columns(2)
    with a:
        respuesta(
            f"<b>1 · Competencia.</b> En {pct(ck['pct_unico'])} de las licitaciones adjudicadas ofertó "
            f"<b>una sola empresa</b>; la mediana es de {num(ck['mediana_oferentes'])} oferentes."
        )
        respuesta(
            f"<b>3 · Concentración.</b> {pct(kk.get('pct_alta'), 0)} de los organismos con al menos {MIN_GRUPO} "
            f"licitaciones adjudicadas tiene sus compras <b>altamente concentradas</b> (HHI > 2.500); en la mediana, "
            f"su principal proveedor se lleva {pct(kk.get('mediana_share_top'), 0)} del monto."
        )
    with b:
        respuesta(
            f"<b>2 · Precio.</b> La mediana adjudica <b>{pct(pk['mediana'], 0)} del monto estimado</b>; "
            f"{pct(pk['pct_sobre'])} se adjudica por sobre lo estimado y {pct(pk['pct_sobre_20'])} lo supera en más "
            f"de 20 %."
        )
        respuesta(
            f"<b>4 · Proceso.</b> De las licitaciones con más de {DIAS_MADUREZ} días cerradas, "
            f"{pct(prk['pct_desierta'])} quedó <b>desierta</b> y {pct(prk['pct_revocada'])} fue revocada. "
            f"Adjudicar toma una mediana de {num(prk['mediana_dias_adjudicar'])} días desde el cierre."
        )

    m = obs.mensual(F)
    fig = go.Figure(
        go.Bar(
            x=m["mes"],
            y=m["publicadas"],
            marker=dict(color=C["s1"], cornerradius=4),
            hovertemplate="%{x|%Y-%m}: %{y:,} licitaciones<extra></extra>",
        )
    )
    st.plotly_chart(layout(fig, title="Licitaciones publicadas por mes"), width="stretch")
    st.markdown(
        '<p class="nota">Los últimos meses aún tienen licitaciones en evaluación: sus tasas de adjudicación '
        "están incompletas.</p>",
        unsafe_allow_html=True,
    )
    tabla(m, "mensual")

# ---------------------------------------------------------------- 1. competencia

with tabs[1]:
    st.subheader("¿Cuántas empresas compiten por cada licitación?")
    ck = obs.competencia_kpis(F)
    respuesta(
        f"De {num(ck['n'])} licitaciones adjudicadas con ofertas registradas, <b>{pct(ck['pct_unico'])} tuvo un solo "
        f"oferente</b>. La mediana es {num(ck['mediana_oferentes'])} oferentes y el promedio "
        f"{num(ck['media_oferentes'], 1)}. Un oferente único no implica irregularidad, pero elimina la presión "
        f"competitiva sobre el precio (ver pregunta 2)."
    )
    c = st.columns(3)
    c[0].metric("Con oferente único", pct(ck["pct_unico"]))
    c[1].metric("Mediana de oferentes", num(ck["mediana_oferentes"]))
    c[2].metric("Adjudicadas analizadas", num(ck["n"]))

    a, b = st.columns(2)
    with a:
        d = obs.distribucion_oferentes(F)
        colores = [C["s2"] if o == "1" else C["s1"] for o in d["oferentes"]]
        fig = go.Figure(
            go.Bar(
                x=d["oferentes"],
                y=d["n"],
                marker=dict(color=colores, cornerradius=4),
                hovertemplate="%{x} oferentes: %{y:,} licitaciones<extra></extra>",
            )
        )
        fig.update_xaxes(title="Oferentes", type="category")
        st.plotly_chart(layout(fig, title="Licitaciones adjudicadas según número de oferentes"), width="stretch")
        tabla(d.drop(columns="orden"), "distribucion_oferentes")
    with b:
        mm = obs.competencia_mensual(F)
        fig = go.Figure(
            go.Scatter(
                x=mm["mes"],
                y=mm["pct_unico"],
                mode="lines+markers",
                line=dict(color=C["s2"], width=2),
                marker=dict(size=8),
                customdata=mm["n"],
                hovertemplate="%{x|%Y-%m}: %{y:.1%} con oferente único (n=%{customdata:,})<extra></extra>",
            )
        )
        fig.update_yaxes(tickformat=".0%", rangemode="tozero")
        st.plotly_chart(layout(fig, title="% con oferente único, por mes de publicación"), width="stretch")
        tabla(mm, "competencia_mensual")

    dims = {"tipo_descripcion": "Tipo", "sector": "Sector", "region_unidad": "Región", "nombre_organismo": "Organismo"}
    dim = st.radio("Comparar por", list(dims), format_func=dims.get, horizontal=True)
    g = obs.competencia_por(F, dim)
    top = g.head(25).iloc[::-1]
    fig = go.Figure(
        go.Bar(
            y=top["grupo"],
            x=top["pct_unico"],
            orientation="h",
            marker=dict(color=C["s2"], cornerradius=4),
            customdata=top[["n", "mediana_oferentes"]],
            hovertemplate="%{y}<br>%{x:.1%} con oferente único<br>n=%{customdata[0]:,} · "
            "mediana %{customdata[1]} oferentes<extra></extra>",
        )
    )
    fig.update_xaxes(tickformat=".0%")
    st.plotly_chart(
        layout(
            fig,
            height=max(300, 24 * len(top) + 60),
            title=f"% con oferente único (grupos con ≥ {MIN_GRUPO} adjudicadas, los 25 más altos)",
        ),
        width="stretch",
    )
    tabla(g, f"competencia_por_{dim}")

# ---------------------------------------------------------------- 2. precio

with tabs[2]:
    st.subheader("¿Se adjudica por sobre o por debajo de lo estimado?")
    pk = obs.precio_kpis(F)
    pc = obs.precio_vs_competencia(F)
    uno = pc.loc[pc["oferentes"] == 1, "mediana"]
    cinco = pc.loc[pc["oferentes"] >= 5, "mediana"]
    frase_comp = ""
    if len(uno) and len(cinco):
        frase_comp = (
            f" Con <b>un oferente</b> la mediana es {pct(uno.iloc[0], 0)} del estimado; con <b>5 o más</b>, "
            f"{pct(cinco.median(), 0)}: más competencia, menor precio relativo."
        )
    respuesta(
        f"En {num(pk['n'])} licitaciones con monto estimado y adjudicado en la misma moneda, la mediana adjudica "
        f"<b>{pct(pk['mediana'], 0)} de lo estimado</b>. {pct(pk['pct_sobre'])} supera el estimado y "
        f"{pct(pk['pct_sobre_20'])} lo supera en más de {SOBRE_PCT} %.{frase_comp}"
    )
    st.markdown(
        f'<p class="nota">Se excluye {pct(pk["pct_precio_unitario"])} de las adjudicadas cuya razón es menor a '
        f"{pct(RAZON_PRECIO_UNITARIO, 0)}: casi siempre convenios de suministro adjudicados por precio unitario "
        "(p. ej. fotocopias a $15 con un estimado de $28 millones), donde la razón no mide precio.</p>",
        unsafe_allow_html=True,
    )
    c = st.columns(4)
    c[0].metric("Mediana adjudicado / estimado", pct(pk["mediana"], 0))
    c[1].metric("Sobre lo estimado", pct(pk["pct_sobre"]))
    c[2].metric(f"Más de {SOBRE_PCT} % sobre", pct(pk["pct_sobre_20"]))
    c[3].metric("Excluidas (precio unitario)", pct(pk["pct_precio_unitario"]))

    a, b = st.columns(2)
    with a:
        h = obs.precio_histograma(F)
        sobre = h["desde"] >= 1.0
        fig = go.Figure()
        for mask, nombre, color in ((~sobre, "Hasta lo estimado", C["s1"]), (sobre, "Sobre lo estimado", C["s2"])):
            hh = h[mask]
            fig.add_bar(
                x=hh["desde"] + 0.05,
                y=hh["n"],
                name=nombre,
                width=0.09,
                marker=dict(color=color, cornerradius=4),
                customdata=["≥ 200 %" if d >= 2 else f"{100 * d:.0f}–{100 * d + 10:.0f} %" for d in hh["desde"]],
                hovertemplate="%{customdata}: %{y:,} licitaciones<extra></extra>",
            )
        fig.update_xaxes(tickformat=".0%", title="Adjudicado / estimado (≥ 200 % agrupado)")
        st.plotly_chart(layout(fig, title="Distribución de adjudicado / estimado"), width="stretch")
        tabla(h, "precio_histograma")
    with b:
        fig = go.Figure(
            go.Scatter(
                x=pc["oferentes"],
                y=pc["mediana"],
                mode="lines+markers",
                line=dict(color=C["s1"], width=2),
                marker=dict(size=9),
                error_y=dict(
                    type="data",
                    symmetric=False,
                    array=pc["p75"] - pc["mediana"],
                    arrayminus=pc["mediana"] - pc["p25"],
                    color=C["neutral"],
                    thickness=1.5,
                    width=0,
                ),
                customdata=pc[["n", "p25", "p75"]],
                hovertemplate="%{x} oferentes: mediana %{y:.0%} (p25 %{customdata[1]:.0%}, p75 %{customdata[2]:.0%},"
                " n=%{customdata[0]:,})<extra></extra>",
            )
        )
        fig.add_hline(y=1, line=dict(color=C["muted"], width=1))
        fig.update_yaxes(tickformat=".0%")
        fig.update_xaxes(title="Oferentes (10 = 10 o más)", dtick=1)
        st.plotly_chart(
            layout(fig, title="Adjudicado / estimado según n.º de oferentes"),
            width="stretch",
        )
        tabla(pc, "precio_vs_competencia")

    pt = obs.precio_por_tipo(F)
    fig = go.Figure(
        go.Bar(
            x=pt["grupo"],
            y=pt["mediana"],
            marker=dict(color=C["s1"], cornerradius=4),
            customdata=pt[["n", "pct_sobre"]],
            hovertemplate="%{x}<br>mediana %{y:.0%}<br>%{customdata[1]:.1%} sobre lo estimado · n=%{customdata[0]:,}"
            "<extra></extra>",
        )
    )
    fig.add_hline(y=1, line=dict(color=C["muted"], width=1))
    fig.update_yaxes(tickformat=".0%")
    st.plotly_chart(layout(fig, title="Mediana adjudicado / estimado por tipo de licitación"), width="stretch")
    tabla(pt, "precio_por_tipo")

# ---------------------------------------------------------------- 3. concentración

with tabs[3]:
    st.subheader("¿Cuán concentradas están las compras en pocos proveedores?")
    orgs = obs.concentracion_organismos(F)
    kk = obs.concentracion_kpis(F)
    mk = obs.concentracion_mercado(F)
    respuesta(
        f"A nivel país el mercado está repartido: los 10 mayores proveedores suman {pct(mk['share_top10'])} del monto "
        f"adjudicado en CLP entre {num(mk['proveedores'])} proveedores. Pero <b>dentro de cada organismo</b> la "
        f"historia cambia: {pct(kk.get('pct_alta'), 0)} de los {num(kk.get('n'))} organismos analizados tiene "
        f"concentración alta (HHI > 2.500) y, en la mediana, su principal proveedor se lleva "
        f"{pct(kk.get('mediana_share_top'), 0)} del monto."
    )
    c = st.columns(4)
    c[0].metric("Top 10 proveedores (país)", pct(mk["share_top10"]))
    c[1].metric("Top 1 % de proveedores", pct(mk["share_top1pct"]))
    c[2].metric("Organismos con HHI > 2.500", pct(kk.get("pct_alta"), 0))
    c[3].metric("Mediana participación del principal", pct(kk.get("mediana_share_top"), 0))

    a, b = st.columns([3, 2])
    with a:
        if not orgs.empty:
            fig = go.Figure(
                go.Scatter(
                    x=orgs["n_lic"],
                    y=orgs["hhi"],
                    mode="markers",
                    marker=dict(size=9, color=C["s1"], opacity=0.75, line=dict(width=2, color="rgba(0,0,0,0)")),
                    customdata=orgs[["nombre_organismo", "proveedor_top", "share_top", "monto_total"]],
                    hovertemplate="<b>%{customdata[0]}</b><br>HHI %{y:,.0f} · %{x:,} licitaciones<br>"
                    "Principal: %{customdata[1]} (%{customdata[2]:.0%})<extra></extra>",
                )
            )
            fig.add_hline(
                y=2500,
                line=dict(color=C["muted"], width=1),
                annotation_text="concentración alta (HHI 2.500)",
                annotation_position="top right",
                annotation_font_color=C["muted"],
            )
            fig.update_xaxes(type="log", title="Licitaciones adjudicadas (escala log)")
            fig.update_yaxes(title="HHI (0–10.000)", range=[0, 10500])
            st.plotly_chart(layout(fig, height=420, title="Concentración por organismo"), width="stretch")
    with b:
        tp = obs.top_proveedores(F, 15).iloc[::-1]
        fig = go.Figure(
            go.Bar(
                y=tp["proveedor"].fillna(tp["codigo_proveedor"]).map(lambda x: x if len(x) <= 30 else x[:29] + "…"),
                x=tp["participacion"],
                orientation="h",
                marker=dict(color=C["s1"], cornerradius=4),
                customdata=tp[["monto", "licitaciones", "organismos"]],
                hovertemplate="%{y}<br>%{x:.2%} del monto<br>%{customdata[1]:,} licitaciones · "
                "%{customdata[2]:,} organismos<extra></extra>",
            )
        )
        fig.update_xaxes(tickformat=".1%", nticks=3, tickangle=0)
        fig.update_yaxes(tickfont=dict(size=11))
        st.plotly_chart(layout(fig, height=420, title="15 mayores proveedores (% del monto en CLP)"), width="stretch")
    st.markdown("**Organismos más concentrados**")
    vista = orgs.assign(share_top=orgs["share_top"].round(3), hhi=orgs["hhi"].round(0))
    st.dataframe(
        vista[["nombre_organismo", "hhi", "share_top", "proveedor_top", "n_proveedores", "n_lic", "monto_total"]],
        width="stretch",
        hide_index=True,
        height=360,
        column_config={
            "nombre_organismo": "Organismo",
            "hhi": st.column_config.NumberColumn("HHI", format="%d"),
            "share_top": st.column_config.ProgressColumn(
                "Principal proveedor", format="percent", min_value=0, max_value=1
            ),
            "proveedor_top": "Proveedor principal",
            "n_proveedores": "Proveedores",
            "n_lic": "Licitaciones",
            "monto_total": st.column_config.NumberColumn("Monto CLP", format="localized"),
        },
    )
    tabla(obs.top_proveedores(F, 200), "top_proveedores")

# ---------------------------------------------------------------- 4. proceso

with tabs[4]:
    st.subheader("¿Cuántas licitaciones fracasan y cuánto demoran?")
    pr = obs.proceso_kpis(F)
    respuesta(
        f"Entre las {num(pr['n'])} licitaciones cerradas hace más de {DIAS_MADUREZ} días, "
        f"{pct(pr['pct_adjudicada'])} se adjudicó, <b>{pct(pr['pct_desierta'])} quedó desierta</b>, "
        f"{pct(pr['pct_revocada'])} fue revocada y {pct(pr['pct_sin_resolver'])} sigue sin resolución en los datos. "
        f"La recepción de ofertas dura una mediana de {num(pr['mediana_dias_oferta'])} días y adjudicar toma "
        f"{num(pr['mediana_dias_adjudicar'])} días más."
    )
    c = st.columns(4)
    c[0].metric("Adjudicadas", pct(pr["pct_adjudicada"]))
    c[1].metric("Desiertas", pct(pr["pct_desierta"]))
    c[2].metric("Días para ofertar (mediana)", num(pr["mediana_dias_oferta"]))
    c[3].metric("Días para adjudicar (mediana)", num(pr["mediana_dias_adjudicar"]))

    a, b = st.columns(2)
    with a:
        pt = obs.proceso_por_tipo(F)
        fig = go.Figure()
        for col, nombre, color in (
            ("adjudicada", "Adjudicada", C["s1"]),
            ("desierta", "Desierta", C["s2"]),
            ("revocada", "Revocada", C["s3"]),
            ("sin_resolver", "Sin resolver", C["s4"]),
        ):
            fig.add_bar(
                y=pt["grupo"],
                x=pt[col],
                name=nombre,
                orientation="h",
                marker=dict(color=color),
                hovertemplate=f"%{{y}}<br>{nombre}: %{{x:.1%}}<extra></extra>",
            )
        fig.update_layout(barmode="stack", bargap=0.3)
        fig.update_traces(marker_line=dict(width=2, color="rgba(0,0,0,0)"))
        fig.update_xaxes(tickformat=".0%", range=[0, 1])
        fig.update_yaxes(autorange="reversed")
        st.plotly_chart(layout(fig, height=400, title="Resultado según tipo de licitación"), width="stretch")
        tabla(pt, "proceso_por_tipo")
    with b:
        fig = go.Figure(
            go.Bar(
                y=pt["grupo"],
                x=pt["dias_adjudicar"],
                orientation="h",
                marker=dict(color=C["s1"], cornerradius=4),
                customdata=pt["dias_oferta"],
                hovertemplate="%{y}<br>%{x} días para adjudicar<br>%{customdata} días de recepción de ofertas"
                "<extra></extra>",
            )
        )
        fig.update_yaxes(autorange="reversed")
        fig.update_xaxes(title="Días (mediana)")
        st.plotly_chart(layout(fig, height=400, title="Días del cierre a la adjudicación"), width="stretch")

    pm = obs.proceso_mensual(F)
    fig = go.Figure(
        go.Scatter(
            x=pm["mes"],
            y=pm["dias_adjudicar"],
            mode="lines+markers",
            line=dict(color=C["s1"], width=2),
            marker=dict(size=8),
            hovertemplate="%{x|%Y-%m}: %{y} días<extra></extra>",
        )
    )
    st.plotly_chart(
        layout(fig, title="Días del cierre a la adjudicación (mediana), por mes de publicación"),
        width="stretch",
    )
    st.markdown(
        '<p class="nota">Los meses recientes se ven más rápidos porque solo incluyen las licitaciones que ya se '
        "adjudicaron (las lentas siguen pendientes).</p>",
        unsafe_allow_html=True,
    )
    tabla(pm, "proceso_mensual")

# ---------------------------------------------------------------- alertas

with tabs[5]:
    st.subheader("Señales de alerta")
    st.markdown(
        "Licitaciones adjudicadas con una o más señales: **oferente único**, **adjudicado más de "
        f"{SOBRE_PCT} % sobre lo estimado** y **plazo de ofertas en el 10 % más corto "
        "de su tipo**. Una señal no prueba una irregularidad: indica dónde vale la pena revisar el expediente."
    )
    ar = obs.alertas_resumen(F)
    tot = ar["n"].sum()
    c = st.columns(4)
    for i, k in enumerate((0, 1, 2, 3)):
        n = int(ar.loc[ar["senales"] == k, "n"].sum())
        frac = n / tot if tot else None
        etiqueta = "<\u00a00,1\u00a0%" if frac is not None and 0 < frac < 0.001 else pct(frac)
        c[i].metric(f"{k} señal{'es' if k != 1 else ''} · {etiqueta}", num(n))
    al = obs.alertas(F)
    st.dataframe(
        al,
        width="stretch",
        hide_index=True,
        column_order=[
            "senales",
            "s_oferente_unico",
            "s_sobre_estimado",
            "s_plazo_corto",
            "codigo_externo",
            "nombre",
            "nombre_organismo",
            "monto_adjudicado",
            "moneda_adjudicada",
            "razon_adjudicado_estimado",
            "n_proveedores_oferentes",
            "dias_publicacion_cierre",
            "tipo_descripcion",
            "fecha_publicacion",
            "monto_estimado",
            "link",
        ],
        height=520,
        column_config={
            "codigo_externo": "Código",
            "nombre": "Licitación",
            "nombre_organismo": "Organismo",
            "tipo_descripcion": "Tipo",
            "fecha_publicacion": st.column_config.DateColumn("Publicada"),
            "dias_publicacion_cierre": "Días para ofertar",
            "n_proveedores_oferentes": "Oferentes",
            "monto_estimado": st.column_config.NumberColumn("Estimado", format="localized"),
            "monto_adjudicado": st.column_config.NumberColumn("Adjudicado", format="localized"),
            "moneda_adjudicada": "Moneda",
            "razon_adjudicado_estimado": st.column_config.NumberColumn("Adj./Est.", format="percent"),
            "s_oferente_unico": st.column_config.CheckboxColumn("Oferente único"),
            "s_sobre_estimado": st.column_config.CheckboxColumn("Sobre estimado"),
            "s_plazo_corto": st.column_config.CheckboxColumn("Plazo corto"),
            "senales": st.column_config.NumberColumn("Señales"),
            "link": st.column_config.LinkColumn("Ficha", display_text="Abrir"),
        },
    )
    st.download_button("Descargar CSV", al.to_csv(index=False).encode("utf-8"), "alertas.csv", "text/csv")

# ---------------------------------------------------------------- metodología

with tabs[6]:
    st.markdown((Path(__file__).resolve().parents[1] / "docs" / "fase3_preguntas.md").read_text())
