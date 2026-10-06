import io
import zipfile

from observatorio import compras

COLS = [
    "Codigo", "Nombre", "Estado", "EsCompraAgil", "EsTratoDirecto", "ProcedenciaOC", "FechaEnvio",
    "CodigoOrganismoPublico", "OrganismoPublico", "RegionUnidadCompra", "CodigoProveedor", "NombreProveedor",
    "MontoTotalOC_PesosChilenos", "RubroN1", "RubroN2", "totalLineaNeto",
]  # fmt: skip


def ag(codigo, fecha, monto, org="O1", prov="P1", rubro="R"):
    return {"codigo": codigo, "fecha": fecha, "tipo": "AG", "org": org, "prov": prov, "rubro": rubro, "monto": monto}


def test_fraccionamiento_tres_en_30_dias_sobre_el_tope():
    topes = {"2026-09": 100.0}
    xs = [ag("a", "2026-09-01", 40), ag("b", "2026-09-10", 40), ag("c", "2026-09-20", 40)]
    (e,) = compras.fraccionamiento(xs, topes)
    assert e["n"] == 3 and e["monto"] == 120 and e["codigos"] == ["a", "b", "c"]


def test_sin_fraccionamiento_si_no_supera_el_tope_o_estan_lejos():
    topes = {"2026-09": 100.0, "2026-10": 100.0}
    bajo = [ag("a", "2026-09-01", 30), ag("b", "2026-09-10", 30), ag("c", "2026-09-20", 30)]
    assert compras.fraccionamiento(bajo, topes) == []
    lejos = [ag("a", "2026-09-01", 60), ag("b", "2026-09-20", 60), ag("c", "2026-10-25", 60)]
    assert compras.fraccionamiento(lejos, topes) == []
    # Otro proveedor no cuenta.
    mixto = [ag("a", "2026-09-01", 60), ag("b", "2026-09-05", 60), ag("c", "2026-09-06", 60, prov="P2")]
    assert compras.fraccionamiento(mixto, topes) == []


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
