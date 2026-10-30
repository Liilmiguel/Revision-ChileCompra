import io
import zipfile

from observatorio import compras

COLS = [
    "Codigo", "Nombre", "Estado", "EsCompraAgil", "EsTratoDirecto", "ProcedenciaOC", "FechaEnvio",
    "CodigoOrganismoPublico", "OrganismoPublico", "RegionUnidadCompra", "CodigoProveedor", "NombreProveedor",
    "MontoTotalOC_PesosChilenos", "RubroN1", "RubroN2", "totalLineaNeto",
]  # fmt: skip


def ag(
    codigo,
    fecha,
    monto,
    org="O1",
    prov="P1",
    rubro="R",
    unidad="U1",
    espec="JERINGA CONTRASTE 200 ML",
    onu="42221500",
    bien=True,
):
    return {"codigo": codigo, "fecha": fecha, "tipo": "AG", "org": org, "prov": prov, "rubro": rubro,
            "rubro2": rubro, "monto": monto, "unidad": unidad, "unidad_nombre": unidad, "espec": espec,
            "onu_principal": onu, "bien": bien}  # fmt: skip


def td(codigo, fecha, monto, causal, **kw):
    return {**ag(codigo, fecha, monto, **kw), "tipo": "TD", "causal": causal}


TOPES = {"2026-09": 100.0, "2026-10": 100.0, "2026-11": 100.0, "2027-03": 100.0}


def test_compra_dividida_misma_especificacion_en_pocos_dias():
    (e,) = compras.compra_dividida([ag("a", "2026-09-01", 60), ag("b", "2026-09-01", 60)], TOPES)
    assert e["n"] == 2 and e["monto"] == 120 and e["iguales"] and e["veces_tope"] == 1.2


def test_compra_dividida_descarta_lo_que_no_es_una_misma_compra():
    par = lambda **kw: [ag("a", "2026-09-01", 60, **kw), ag("b", "2026-09-02", 60, **kw)]  # noqa: E731
    assert compras.compra_dividida(par(bien=False), TOPES) == []  # servicio (p. ej. un examen por paciente)
    assert compras.compra_dividida(par(espec="VER ARCHIVO ADJUNTO"), TOPES) == []  # especificación genérica
    assert compras.compra_dividida(par(espec="EXAMEN MIBI STRESS"), TOPES) == []  # servicio con código de bien
    # Otra unidad de compra del mismo organismo (otro hospital), otra especificación o lejos en el tiempo.
    assert compras.compra_dividida([ag("a", "2026-09-01", 60), ag("b", "2026-09-01", 60, unidad="U2")], TOPES) == []
    assert (
        compras.compra_dividida([ag("a", "2026-09-01", 60), ag("b", "2026-09-01", 60, espec="GASA ESTERIL")], TOPES)
        == []
    )
    assert compras.compra_dividida([ag("a", "2026-09-01", 60), ag("b", "2026-09-20", 60)], TOPES) == []
    assert compras.compra_dividida([ag("a", "2026-09-01", 40), ag("b", "2026-09-01", 40)], TOPES) == []  # bajo el tope


def test_compras_repetidas_mismo_producto_y_sin_las_ya_divididas():
    xs = [ag("a", "2026-09-01", 40, espec="KIT B12"), ag("b", "2026-09-10", 40, espec="KIT FERRITINA"),
          ag("c", "2026-09-20", 40, espec="KIT CREATININA")]  # fmt: skip
    (e,) = compras.compras_repetidas(xs, TOPES, set())
    assert e["n"] == 3 and e["codigos"] == ["a", "b", "c"]
    assert compras.compras_repetidas(xs, TOPES, {"a"}) == []
    otro = [*xs[:2], ag("c", "2026-09-20", 40, onu="51101500")]  # otro producto
    assert compras.compras_repetidas(otro, TOPES, set()) == []


def test_emergencia_repetida_solo_bienes_y_a_lo_largo_de_meses():
    em = "Emergencia, urgencia o imprevisto"
    xs = [td("a", "2026-09-01", 9, em), td("b", "2026-11-01", 9, em), td("c", "2027-03-15", 9, em)]
    (e,) = compras.emergencia_repetida(xs)
    assert e["n"] == 3
    assert compras.emergencia_repetida([{**x, "bien": False, "onu_principal": "85101500"} for x in xs]) == []
    assert compras.emergencia_repetida(xs[:2]) == []
    juntas = [td("a", "2026-09-01", 9, em), td("b", "2026-09-05", 9, em), td("c", "2026-09-09", 9, em)]
    assert compras.emergencia_repetida(juntas) == []  # una sola emergencia, comprada en partes


def test_td_encadenados_de_causales_menores():
    menor = "Costo de evaluación desproporcionado, y por monto de contratación inferior a 100 UTM"
    lim = compras.ENCADENADO_UTM * compras.UTM_CLP
    xs = [td("a", "2026-09-01", 0.6 * lim, menor), td("b", "2026-09-15", 0.6 * lim, menor)]
    (e,) = compras.td_encadenados(xs)
    assert e["n"] == 2 and e["causal"] == menor
    assert compras.td_encadenados([{**x, "espec": "REALIZAR EXAMEN MIBI STRESS"} for x in xs]) == []
    assert compras.td_encadenados([{**x, "causal": "Emergencia, urgencia o imprevisto"} for x in xs]) == []


def test_tope_mes_percentil_alto():
    xs = [ag(str(i), "2026-09-01", 1 + i % 1000) for i in range(5000)]
    assert 995 <= compras.tope_mes(xs) <= 1000
    assert compras.tope_mes(xs[:10]) is None


def test_leer_mes_agrega_items_y_omite_canceladas(tmp_path):
    def fila(codigo, estado="Aceptada", agil="Si", rubro="R1", neto="10", monto="100"):
        v = {c: "NA" for c in COLS}
        v.update(
            Codigo=codigo, Nombre="Compra", Estado=estado, EsCompraAgil=agil, EsTratoDirecto="No",
            FechaEnvio="2026-09-03", CodigoOrganismoPublico="7", OrganismoPublico="Org", CodigoProveedor="9",
            NombreProveedor="Prov", MontoTotalOC_PesosChilenos=monto, RubroN1=rubro, RubroN2=rubro + "x",
            totalLineaNeto=neto,
        )  # fmt: skip
        return ";".join(f'"{v[c]}"' for c in COLS)

    filas = [fila("A", rubro="Chico", neto="5"), fila("A", rubro="Grande", neto="90"), fila("B", estado="Cancelada"),
             fila("C", agil="No")]  # fmt: skip
    csv = "\r\n".join([";".join(f'"{c}"' for c in COLS), *filas]) + "\r\n"
    z = tmp_path / "oc.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("2026-9.csv", io.BytesIO(csv.encode("cp1252")).getvalue())
    (oc,) = compras.leer_mes(z)
    assert oc["codigo"] == "A" and oc["tipo"] == "AG" and oc["rubro"] == "Grande" and oc["monto"] == 100.0


def test_meses_cerrados_excluye_el_actual():
    from datetime import date

    assert compras.meses_cerrados(date(2026, 1, 15), 3) == ["2025-10", "2025-11", "2025-12"]


def test_por_proveedor_suma_compras_agiles_y_tratos_directos():
    xs = [
        {**ag("a", "2026-09-01", 40), "prov_nombre": "P", "prov_rut": "1-9", "banda": True},
        {**ag("b", "2026-09-02", 60, org="O2"), "prov_nombre": "P", "prov_rut": "1-9"},
        {**ag("c", "2026-09-03", 500), "tipo": "TD", "causal": "Emergencia, urgencia o imprevisto", "prov_nombre": "P"},
    ]
    (fila,) = compras.por_proveedor(xs, {"a"})
    d = dict(zip(compras.CAMPOS_PROVEEDOR, fila, strict=True))
    assert d["ag_n"] == 2 and d["ag_monto"] == 100 and d["ag_banda"] == 1 and d["ag_fracc"] == 1
    assert d["td_n"] == 1 and d["td_monto"] == 500 and d["td_emergencia"] == 1 and d["orgs"] == 2 and d["rut"] == "1-9"
