from observatorio import precios


def oc(tipo="AG", org="O1", prov="P1", monto=0.0):
    return {
        "tipo": tipo,
        "fecha": "2026-09-01",
        "org": org,
        "prov": prov,
        "monto": monto,
        "opaca": False,
        "producto": "x",
    }


def test_clave_ignora_tildes_signos_y_corta_en_diez_palabras():
    k = precios.clave("51171910", "Caja", "Paracetamol 500 mg, comprimidos (caja de 20) — genérico bioequivalente")
    assert k == ("51171910", "CAJA", "PARACETAMOL 500 MG COMPRIMIDOS CAJA DE 20 GENERICO BIOEQUIVALENTE")
    # Servicios y unidades que no son cantidades no se comparan.
    assert precios.clave("92121504", "Unidad", "Servicio de guardias") is None
    assert precios.clave("56101700", "Unidad", "Servicio de arriendo de carpa") is None
    assert precios.clave("42295400", "Unidad", "Insumos cirugía de prótesis según detalle") is None
    assert precios.clave("51171910", "Global", "Paracetamol") is None
    # Convenio marco: sin unidad pero con código de catálogo.
    assert precios.clave("0", None, "4511954 Pepino fresco") == ("0", "CATALOGO", "4511954 PEPINO FRESCO")


def test_sobre_la_mediana_solo_compras_directas_y_con_exceso_minimo():
    k = ("1", "UNIDAD", "GUANTE")
    ocs = {f"r{i}": oc("SE", org=f"O{i % 3}") for i in range(6)}
    ocs["caro"] = oc("TD", prov="PX")
    ocs["caro_se"] = oc("SE")
    lineas = [(k, 100.0, 10, f"r{i}") for i in range(6)] + [(k, 1000.0, 5000, "caro"), (k, 1000.0, 5000, "caro_se")]
    r = precios.analizar(lineas, ocs)
    (fila,) = r["sobre_mediana"]
    d = dict(zip(r["campos_sobre"], fila, strict=True))
    assert d["oc"] == "caro" and d["mediana"] == 100 and d["razon"] == 10.0 and d["exceso"] == 900 * 5000
    assert r["exceso_proveedor"] == {"PX": [4_500_000, 1]}


def test_mismo_proveedor_precios_distintos():
    k = ("1", "CAJA", "TRIKAFTA")
    ocs = {"a": oc("TD", prov="S"), "b": oc("TD", prov="S"), "c": oc("TD", prov="S")}
    lineas = [(k, 8_000_000.0, 10, "a"), (k, 16_000_000.0, 15, "b"), (k, 16_000_000.0, 1, "c")]
    (fila,) = precios.analizar(lineas, ocs)["mismo_proveedor"]
    assert fila[0] == "S" and fila[5] == 8_000_000 and fila[6] == 16_000_000 and fila[7] == 2.0
    assert fila[8] == 8_000_000 * 16 and fila[10][0] in ("b", "c")


def test_orden_sin_precio_unitario_sobre_1000_utm():
    ocs = {"op": {**oc("TD", monto=200e9), "opaca": True}, "chica": {**oc("TD", monto=1e6), "opaca": True}}
    r = precios.analizar([], ocs)
    assert [x[0] for x in r["sin_precio_unitario"]] == ["op"]


def test_linea_de_cantidad_1_a_100_veces_la_mediana_es_contrato_sin_precio_unitario():
    k = ("1", "UNIDAD", "PEMBROLIZUMAB")
    ocs = {f"r{i}": oc("TD", org=f"O{i}") for i in range(5)}
    ocs["contrato"] = oc("TD", monto=57e9)
    lineas = [(k, 1_740_000.0, 10, f"r{i}") for i in range(5)] + [(k, 57e9, 1, "contrato")]
    r = precios.analizar(lineas, ocs)
    assert r["sobre_mediana"] == [] and r["mismo_proveedor"] == []
    assert [x[0] for x in r["sin_precio_unitario"]] == ["contrato"]
