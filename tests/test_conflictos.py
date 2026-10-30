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


def test_emparejar_no_confunde_organismos_con_el_mismo_lugar():
    orgs = {
        "1": "UNIVERSIDAD DE O'HIGGINS",
        "2": "GOBIERNO REGIONAL DE O'HIGGINS",
        "3": "CORP ADMINISTRATIVA DEL PODER JUDICIAL",
    }
    assert conflictos.emparejar_organismo("Gobierno Regional de O'Higgins", orgs) == ("2", 1.0)
    assert conflictos.emparejar_organismo("Poder Judicial", orgs)[1] < conflictos.MIN_SIMILITUD
    assert conflictos.emparejar_organismo("Corporacion Administrativa del Poder Judicial", orgs) == ("3", 1.0)


def test_sociedad_declarada_por_muchos_es_abierta():
    part = [{"rut_sociedad": "89862200-2", "declarante_nombre": n, "servicio": "Ministerio Publico"} for n in "ABC"]
    part.append({"rut_sociedad": "76111111-1", "declarante_nombre": "D", "servicio": "Ministerio Publico"})
    orgs = {"1": "MINISTERIO PUBLICO"}
    oc = {("1", "89862200-2"): [5, 100.0, {"SE"}], ("1", "76111111-1"): [1, 10.0, {"TD"}]}
    r = conflictos.cruzar(part, oc, {}, orgs, {})
    abiertas = {c["declarante"]: c["abierta"] for c in r["conflictos"]}
    assert abiertas == {"A": True, "B": True, "C": True, "D": False}
