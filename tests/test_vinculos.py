from observatorio import vinculos


def test_clave_direccion_sin_oficina_y_con_numero():
    k = vinculos.clave_direccion("Avda. El Golf 99, Of. 701", "Las Condes")
    assert k == "AVDA EL GOLF 99 | LAS CONDES"
    assert vinculos.clave_direccion("Sin información", "Santiago") is None


def test_clave_contacto_descarta_genericos():
    assert vinculos.clave_contacto("Juan Pérez") == "JUAN PEREZ"
    assert vinculos.clave_contacto("Ventas Empresa") is None
    assert vinculos.clave_contacto("Juan") is None


def test_grupos_une_por_direccion_o_contacto_y_descarta_valores_muy_compartidos():
    d = lambda dir_, c=None: {"direccion": dir_, "comuna": "Stgo", "contacto": c}  # noqa: E731
    cache = {
        "A": d("Calle 1 123", "Ana Soto"),
        "B": d("Calle 1 123"),
        "C": d("Otra 9", "Ana Soto"),
        "D": d("Lejos 5"),
        # una oficina contable con 7 clientes no vincula
        **{f"X{i}": d("Contador 77") for i in range(vinculos.MAX_COMPARTIDO + 1)},
    }
    gs, aristas, descartes = vinculos.grupos(cache)
    assert gs == [["A", "B", "C"]]
    assert {t for *_, t in aristas} == {"direccion", "contacto"}
    assert descartes == {"direccion": 1, "contacto": 0}


def test_resumir_cuenta_competencia_entre_miembros():
    pares = {("A", "B"): {"juntos": 6, "solos": 5, "identicas": 2, "gana_a": 3, "gana_b": 3},
             ("A", "Z"): {"juntos": 9, "solos": 0, "identicas": 0, "gana_a": 1, "gana_b": 0}}  # fmt: skip
    (g,) = vinculos.resumir([["A", "B"]], [("A", "B", "direccion")], pares, {"A": ["Alfa", "1-9"]}, {"A": [10, 5]})
    assert g["juntos"] == 6 and g["solos"] == 5 and g["identicas"] == 2 and g["vinculos"] == ["direccion"]
    assert g["monto"] == 15 and g["miembros"][0] == ["A", "Alfa", "1-9", 10, 5]


def test_candidatos():
    pares = {
        ("A", "B"): {"juntos": 2, "solos": 0, "identicas": 1},
        ("C", "D"): {"juntos": 6, "solos": 4, "identicas": 0},
        ("E", "F"): {"juntos": 9, "solos": 1, "identicas": 0},
    }
    assert vinculos.candidatos(pares, [("G", "H")]) == {"A", "B", "C", "D", "G", "H"}
