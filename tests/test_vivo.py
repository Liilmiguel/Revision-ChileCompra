from datetime import date

from observatorio import vivo


def fila(prov, correlativo, pu, total=None, estado="Aceptada"):
    return {
        "CodigoProveedor": prov,
        "NombreProveedor": f"Prov {prov}",
        "RutProveedor": prov,
        "Correlativo": correlativo,
        "MontoUnitarioOferta": str(pu).replace(".", ","),
        "Valor Total Ofertado": str(total if total is not None else pu),
        "Estado Oferta": estado,
        "Moneda de la Oferta": "Peso Chileno",
    }


def test_oferta_muy_baja_entre_pares_del_mismo_alcance():
    # Cuatro oferentes con 1 línea: A = 20 frente a 100, 110, 90 (mediana de las otras: 100).
    filas = [fila("A", "1", 20), fila("B", "1", 100), fila("C", "1", 110), fila("D", "1", 90)]
    of = {o["prov"]: o for o in vivo.analizar_ofertas(filas, estimado=120)}
    assert of["A"]["clase"] == "muy_baja" and of["A"]["razon_pares"] == 0.2
    assert of["B"]["clase"] is None and of["D"]["clase"] is None


def test_posible_error_y_precio_unitario():
    filas = [fila("A", "1", 2), fila("B", "1", 100), fila("C", "1", 110), fila("D", "1", 90)]
    assert vivo.analizar_ofertas(filas)[0]["clase"] == "posible_error"
    # Si las ofertas son mucho menores que el estimado, es un suministro a precio unitario: no se compara.
    assert all(o["razon_pares"] is None for o in vivo.analizar_ofertas(filas, estimado=1_000_000))


def test_sin_comparacion_con_menos_de_tres_del_mismo_alcance():
    # A ofrece 2 líneas y B, C 1 línea: ningún grupo llega a 3.
    filas = [fila("A", "1", 10), fila("A", "2", 10), fila("B", "1", 100), fila("C", "1", 100)]
    assert all(o["clase"] is None for o in vivo.analizar_ofertas(filas))


def test_rechazada_y_orden_por_total():
    of = vivo.analizar_ofertas([fila("A", "1", 50, estado="Rechazada"), fila("B", "1", 30)])
    assert [o["prov"] for o in of] == ["B", "A"]
    assert of[1]["rechazada"]


def test_meses_recientes_cruza_el_anio():
    assert vivo.meses_recientes(date(2026, 2, 15), 4) == ["2025-11", "2025-12", "2026-1", "2026-2"]


def test_resumen_detalle_no_guarda_funcionarios():
    d = {
        "CodigoExterno": "1-1-LE26",
        "Nombre": "X",
        "CodigoEstado": 5,
        "Tipo": "LE",
        "Comprador": {"CodigoOrganismo": "7", "NombreOrganismo": "Org", "NombreUsuario": "Persona"},
        "Fechas": {"FechaPublicacion": "2026-10-01T10:00:00", "FechaCierre": "2026-10-09T15:00:00"},
        "MontoEstimado": 1000.0,
        "NombreResponsableContrato": "Otra persona",
    }
    r = vivo.resumen_detalle(d)
    assert r["cierre"] == "2026-10-09T15:00" and r["publicada"] == "2026-10-01"
    assert "Persona" not in str(r) and "Otra persona" not in str(r)


def test_compactar_guarda_cada_proveedor_una_vez():
    lics = [
        {"codigo": c, "ofertas": vivo.analizar_ofertas([fila("A", "1", 10), fila("B", "1", 12)])} for c in ("x", "y")
    ]
    out, provs = vivo.compactar(lics)
    assert provs == {"A": ["Prov A", "A"], "B": ["Prov B", "B"]}
    assert out[0]["ofertas"][0] == ["A", 10.0, 1, 0, None, None]
    assert len(out[0]["ofertas"][0]) == len(vivo.CAMPOS_OFERTA)
