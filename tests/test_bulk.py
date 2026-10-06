import io
import zipfile

import pytest

from observatorio import bulk
from observatorio.load_raw import split_rows

# CSV sintético con las trampas reales de la descarga masiva: fin de línea CR, CR
# embebido en un campo, cp1252 (0xE9 = é), UTF-8 incrustado (C3 81 = Á), un byte
# que cp1252 no define (0x81), nulos 'NA' y cabecera con columna duplicada '.1'.
CSV = (
    b'"CodigoExterno";"Nombre";"Descripcion";"Desc.1";"MontoEstimado";"Correlativo";"CodigoProveedor"\r'
    b'"1-1-LE26";"Caf\xe9";"linea uno\rlinea dos";NA;"1,4e+07";"1";"10"\r'
    b'"1-1-LE26";"Caf\xe9";"linea uno\rlinea dos";NA;"1,4e+07";"1";"11"\r'
    b'"2-2-LP26";"TINTA P\xc3\x81";"raro \x81";"x";"NA";"1";"10"\r'
)


def rows():
    return list(bulk.read_csv(io.TextIOWrapper(io.BytesIO(CSV), encoding="latin-1", newline="")))


def test_read_csv_decodifica_y_respeta_campos_multilinea():
    r = rows()
    assert len(r) == 3
    assert r[0]["Nombre"] == "Café"
    assert r[0]["Descripcion"] == "linea uno\rlinea dos"
    assert r[0]["Desc.1"] is None
    assert r[2]["Nombre"] == "TINTA PÁ"
    assert r[2]["Descripcion"] == "raro \x81"
    assert r[2]["MontoEstimado"] is None


def test_read_rows_desde_zip(tmp_path):
    path = tmp_path / "lic_2026-8.zip"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("lic_2026-8.csv", CSV)
    assert len(list(bulk.read_rows(path))) == 3


def test_fila_con_columnas_de_mas_falla():
    bad = b'"a";"b"\r"1";"2";"3"\r'
    with pytest.raises(ValueError):
        list(bulk.read_csv(io.TextIOWrapper(io.BytesIO(bad), encoding="latin-1", newline="")))


def test_split_rows_es_sin_perdida():
    original = rows()
    heads, lines = split_rows(original)
    lines = list(lines)
    assert set(heads) == {"1-1-LE26", "2-2-LP26"}
    assert lines[0][2] == {}  # la primera fila de cada licitación es la cabecera
    assert lines[1][2] == {"CodigoProveedor": "11"}
    for (_, code, diff), row in zip(lines, original, strict=True):
        assert heads[code] | diff == row


@pytest.mark.parametrize(
    ("start", "end", "expected"),
    [
        ("2025-11", "2026-2", ["2025-11", "2025-12", "2026-1", "2026-2"]),
        ("2026-8", "2026-8", ["2026-8"]),
        ("2026-9", "2026-8", []),
    ],
)
def test_months_between(start, end, expected):
    assert bulk.months_between(start, end) == expected


def test_mes_invalido():
    with pytest.raises(ValueError):
        bulk.parse_month("2026-13")


def test_registros_malformados_se_descartan_y_cuentan():
    # Un byte dañado en origen ("P"DRO) desarma el entrecomillado de ese registro.
    data = b'"a";"b"\r"1";"2"\r"P"DRO";"x";"y"\r"3";"4"\r'
    stats = {}
    rows = list(
        bulk.read_csv(io.TextIOWrapper(io.BytesIO(data), encoding="latin-1", newline=""), stats, max_malformados=0.5)
    )
    assert rows == [{"a": "1", "b": "2"}, {"a": "3", "b": "4"}]
    assert stats == {"registros": 3, "malformados": 1}


def test_demasiados_malformados_falla():
    data = b'"a";"b"\r"1";"2"\r"P"DRO";"x";"y"\r'
    with pytest.raises(bulk.DemasiadosMalformados):
        list(bulk.read_csv(io.TextIOWrapper(io.BytesIO(data), encoding="latin-1", newline=""), max_malformados=0.1))
