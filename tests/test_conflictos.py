from observatorio import conflictos


def test_normalizar_rut():
    assert conflictos.normalizar_rut("77.634.874-0") == "77634874-0"
    assert conflictos.normalizar_rut("9.633.707-k") == "9633707-K"
    assert conflictos.normalizar_rut("") is None


def test_emparejar_organismo_tolera_prefijos():
    orgs = {"1": "I MUNICIPALIDAD DE PUENTE ALTO", "2": "I MUNICIPALIDAD DE PUERTO MONTT", "3": "MINISTERIO DE SALUD"}
    assert conflictos.emparejar_organismo("Ilustre Municipalidad de Puente Alto", orgs) == ("1", 1.0)
    org, sim = conflictos.emparejar_organismo("Universidad de Talca", orgs)
    assert sim < conflictos.MIN_SIMILITUD


def test_cruzar_detecta_venta_al_propio_organismo():
    muni = "Municipalidad de Puente Alto"
    part = [
        {"rut_sociedad": "76.111.111-1", "nombre_sociedad": "Soc A", "declarante_nombre": "Funcionario X",
         "cargo": "Jefe", "servicio": "Ilustre " + muni},
        {"rut_sociedad": "76.222.222-2", "declarante_nombre": "Funcionario Y", "servicio": muni},
        {"rut_sociedad": "76.333.333-3", "declarante_nombre": "Funcionario Z", "servicio": muni},
    ]  # fmt: skip
    orgs = {"1": "I MUNICIPALIDAD DE PUENTE ALTO", "2": "MINISTERIO DE SALUD"}
    oc = {("1", "76111111-1"): [3, 900.0, {"AG"}], ("2", "76222222-2"): [1, 50.0, {"TD"}]}
    r = conflictos.cruzar(part, oc, {}, orgs, {})
    (c,) = r["conflictos"]
    assert c["declarante"] == "Funcionario X" and c["org"] == "1" and c["oc_n"] == 3 and c["oc_monto"] == 900
    # Y tiene participación en un proveedor del Estado, pero no de su organismo; Z en ninguno.
    assert {x["declarante"] for x in r["participaciones_en_proveedores"]} == {"Funcionario X", "Funcionario Y"}
