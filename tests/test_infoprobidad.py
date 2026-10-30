from observatorio import infoprobidad


def test_dv_y_rut():
    assert infoprobidad.dv(76052170) == "1"
    assert infoprobidad.dv(97036000) == "K"
    assert infoprobidad.rut_sociedad("77354770") == "77354770-" + infoprobidad.dv(77354770)
    assert infoprobidad.rut_sociedad("1e+006") is None and infoprobidad.rut_sociedad("") is None


def test_usa_la_ultima_declaracion_y_enlaza_la_ficha():
    def decl(uri, quien, fecha, inst):
        return {"UriDeclaracion": uri, "UriDeclarante": "x/" + quien, "Tipo": "T", "Nombre": "ANA", "ApPaterno": quien,
                "ApMaterno": "", "Declaracion": fecha, "Institucion": inst, "Cargo": "CONCEJAL"}  # fmt: skip

    decls = [decl("d1", "PEREZ", "2024-03-01", "MUNI A"), decl("d2", "PEREZ", "2026-03-01", "MUNI B")]
    acc = [
        {"UriDeclaracion": "d1", "RutJuridica": "76052170", "EntidadAccion": "VIEJA", "Pais": "CHILE"},
        {"UriDeclaracion": "d2", "RutJuridica": "76052170", "EntidadAccion": "NUEVA", "Pais": "PERU"},
        {"UriDeclaracion": "d2", "RutJuridica": "", "EntidadAccion": "SIN RUT"},
    ]
    url = "https://www.infoprobidad.cl/Declaracion/Declaracion?ID=1"
    fichas = [
        {"declarante_nombre": "Ana Pérez", "fecha_declaracion": "2026-03-01", "url_declaracion": url,
         "titular": "declarante", "rut_sociedad": "76052170-1"},
        {"declarante_nombre": "Ana Pérez", "fecha_declaracion": "2026-03-01", "url_declaracion": url,
         "titular": "cónyuge", "rut_sociedad": "77777777-7"},
        {"declarante_nombre": "Ana Pérez", "fecha_declaracion": "2024-03-01", "titular": "cónyuge",
         "rut_sociedad": "78888888-8"},
    ]  # fmt: skip
    r = infoprobidad.participaciones(decls, acc, fichas)
    f, conyuge = r["filas"]
    assert conyuge["rut_sociedad"] == "77777777-7" and r["de_otros_titulares"] == 1
    assert f["nombre_sociedad"] == "NUEVA" and f["servicio"] == "MUNI B" and f["rut_sociedad"] == "76052170-1"
    assert f["extranjera"] and f["url_declaracion"].endswith("ID=1") and r["descartadas_sin_rut"] == 1
