"""Métricas de las 4 preguntas sobre un snapshot sintético con resultados conocidos."""

import json
from datetime import date

import pytest

pa = pytest.importorskip("pyarrow")
pq = pytest.importorskip("pyarrow.parquet")
pytest.importorskip("duckdb")

from observatorio.metricas import Filtros, Observatorio  # noqa: E402


def lic(
    codigo,
    org,
    *,
    estado="Adjudicada",
    oferentes=2,
    estimado=100.0,
    adjudicado=90.0,
    cierre=date(2024, 1, 10),
    dias_adj=20,
    plazo=10,
    tipo="LE",
    descalificada=False,
):
    adj = estado == "Adjudicada"
    unico = adj and oferentes == 1
    sobre = adj and adjudicado / estimado > 1.2
    desc = adj and descalificada
    return {
        # Señales y puntaje como los calcula dbt (int_licitacion_senales), con sus pesos.
        "s_oferente_unico": unico,
        "s_competencia_descalificada": desc,
        "s_sobre_oferta_barata": False,
        "s_sobre_estimado": sobre,
        "s_plazo_corto": False,
        "s_precio_referencia": False,
        "razon_sobre_mas_barata": None,
        "puntaje_riesgo": 25 * unico + 25 * desc + 15 * sobre,
        "codigo_externo": codigo,
        "nombre": codigo,
        "tipo": tipo,
        "tipo_descripcion": tipo,
        "tipo_orden": 1,
        "codigo_organismo": org,
        "nombre_organismo": f"Org {org}",
        "sector": "Salud",
        "region_unidad": "RM",
        "codigo_estado": 8 if adj else 7,
        "estado_grupo": estado,
        "estado_es_final": True,
        "fuente_estado": "masiva",
        "fecha_publicacion": date(2024, 1, 1),
        "mes_publicacion": date(2024, 1, 1),
        "fecha_cierre": cierre,
        "dias_publicacion_cierre": plazo,
        "fecha_adjudicacion": cierre if adj else None,
        "dias_cierre_adjudicacion": dias_adj if adj else None,
        "moneda": "CLP",
        "monto_estimado": estimado,
        "monto_estimado_visible": True,
        "monto_adjudicado": adjudicado if adj else None,
        "monto_adjudicado_bruto": adjudicado if adj else None,
        "moneda_adjudicada": "CLP" if adj else None,
        "razon_adjudicado_estimado": adjudicado / estimado if adj else None,
        "numero_oferentes": oferentes,
        "n_proveedores_oferentes": oferentes,
        "n_proveedores_adjudicados": 1 if adj else 0,
        "es_oferente_unico": oferentes == 1,
        "n_lineas_atipicas": 0,
        "link": "",
    }


@pytest.fixture
def obs(tmp_path):
    lics = (
        # Organismo A: 3 adjudicadas, una con oferente único y sobre lo estimado.
        [lic("A1", "A", oferentes=1, adjudicado=150.0), lic("A2", "A"), lic("A3", "A", oferentes=5, adjudicado=50.0)]
        # A4: suministro adjudicado por precio unitario (5 % del estimado): fuera de la pregunta 2.
        + [lic("A4", "A", oferentes=3, adjudicado=5.0)]
        # Organismo B: 1 adjudicada y 1 desierta.
        + [lic("B1", "B", oferentes=3, descalificada=True), lic("B2", "B", estado="Desierta", oferentes=0)]
        # Una licitación reciente (no madura) que no cuenta para la pregunta 4.
        + [lic("C1", "B", estado="Desierta", cierre=date(2024, 12, 1))]
    )
    lics[-1]["fecha_publicacion"] = date(2024, 12, 1)
    adjs = [
        {"codigo_externo": "A1", "codigo_proveedor": "P1", "moneda": "CLP", "n_lineas": 1, "monto_adjudicado": 150.0},
        {"codigo_externo": "A2", "codigo_proveedor": "P1", "moneda": "CLP", "n_lineas": 1, "monto_adjudicado": 90.0},
        {"codigo_externo": "A3", "codigo_proveedor": "P2", "moneda": "CLP", "n_lineas": 1, "monto_adjudicado": 60.0},
        {"codigo_externo": "B1", "codigo_proveedor": "P2", "moneda": "CLP", "n_lineas": 1, "monto_adjudicado": 90.0},
    ]
    provs = [
        {
            "codigo_proveedor": p,
            "rut_proveedor": p,
            "nombre_proveedor": f"Prov {p}",
            "razon_social_proveedor": p,
            "n_licitaciones_ofertadas": 10,
            "n_licitaciones_adjudicadas": 2,
        }
        for p in ("P1", "P2")
    ]
    pares = [{"ganador": "P1", "acompanante": "P2", "juntos": 6, "gana_ganador": 6}]
    for name, rows in (
        ("licitaciones", lics),
        ("adjudicaciones", adjs),
        ("proveedores", provs),
        ("pares", pares),
    ):
        pq.write_table(pa.Table.from_pylist(rows), tmp_path / f"{name}.parquet")
    (tmp_path / "meta.json").write_text(json.dumps({"generado": "2024-12-31", "corte_datos": "2024-12-31"}))
    return Observatorio(tmp_path)


def test_competencia(obs):
    k = obs.competencia_kpis(Filtros())
    assert k["n"] == 5
    assert k["pct_unico"] == pytest.approx(0.2)


def test_precio(obs):
    k = obs.precio_kpis(Filtros())
    assert k["n"] == 4  # A4 (5 % del estimado) queda fuera
    assert k["pct_precio_unitario"] == pytest.approx(0.2)
    assert k["pct_sobre"] == pytest.approx(0.25)  # solo A1 (150 %)
    assert k["mediana"] == pytest.approx(0.9)


def test_concentracion_hhi(obs):
    orgs = obs.concentracion_organismos(Filtros(), min_lic=1).set_index("codigo_organismo")
    # Organismo A: P1 = 240, P2 = 60 → shares 0,8 y 0,2 → HHI = 6.400 + 400.
    assert orgs.loc["A", "hhi"] == pytest.approx(6800)
    assert orgs.loc["A", "share_top"] == pytest.approx(0.8)
    assert orgs.loc["A", "proveedor_top"] == "Prov P1"
    assert orgs.loc["B", "hhi"] == pytest.approx(10000)


def test_proceso_solo_maduras(obs):
    k = obs.proceso_kpis(Filtros())
    assert k["n"] == 6  # C1 cerró hace menos de 120 días respecto del corte
    assert k["pct_desierta"] == pytest.approx(1 / 6)


def test_filtros(obs):
    assert obs.competencia_kpis(Filtros(organismos=["B"]))["n"] == 1
    assert obs.resumen(Filtros(desde=date(2024, 6, 1)))["n"] == 1


def test_alertas_niveles(obs):
    r = obs.alertas_resumen(Filtros())
    # Adjudicadas: A1 (único + sobre estimado = 40), B1 (descalificada = 25), A2, A3, A4 (0).
    assert (r["n"], r["alto"], r["medio"], r["sin"]) == (5, 1, 1, 3)
    assert r["monto_alto"] == pytest.approx(150)
    assert r["s_competencia_descalificada"] == pytest.approx(0.2)
    al = obs.alertas(Filtros()).set_index("codigo_externo")
    assert list(al.index) == ["A1"]
    assert set(obs.alertas(Filtros(), min_puntaje=20)["codigo_externo"]) == {"A1", "B1"}


def test_proveedores_riesgo(obs):
    pr = obs.proveedores_riesgo(Filtros(), min_lic=1).set_index("codigo_proveedor")
    p1, p2 = pr.loc["P1"], pr.loc["P2"]
    # P1 gana A1 (150) y A2 (90) en el organismo A, que gasta 300 en total.
    assert (p1["n_lic"], p1["n_alto"], p1["max_unico_org"], p1["n_acompanantes"]) == (2, 1, 1, 1)
    assert p1["monto_alto"] == pytest.approx(150)
    assert p1["pct_unico"] == pytest.approx(0.5)
    assert p1["dependencia"] == pytest.approx(1.0)
    assert p1["captura"] == pytest.approx(0.8)
    # P2 gana A3 (60, organismo A) y B1 (90, organismo B): su principal es B, donde lo capta todo.
    assert p2["organismo_principal"] == "Org B"
    assert p2["dependencia"] == pytest.approx(0.6)
    assert p2["captura"] == pytest.approx(1.0)
    assert list(pr.index) == ["P1", "P2"]  # orden: monto en riesgo alto


def test_organismos_y_ficha(obs):
    org = obs.organismos_riesgo(Filtros(), min_lic=1).set_index("codigo_organismo")
    assert org.loc["A", "n"] == 4
    assert org.loc["A", "pct_alto"] == pytest.approx(0.25)
    assert org.loc["B", "pct_descalificada"] == pytest.approx(1.0)
    ficha = obs.proveedor("P1", Filtros())
    assert set(ficha["licitaciones"]["codigo_externo"]) == {"A1", "A2"}
    assert ficha["acompanantes"]["acompanante"].tolist() == ["Prov P2"]
