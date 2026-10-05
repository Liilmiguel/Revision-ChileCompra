"""Descarga masiva mensual de licitaciones (transparenciachc.blob.core.windows.net).

Formato verificado en la Fase 0 (docs/fase0_hallazgos.md): un CSV por zip,
separador `;`, nulos `NA`, fin de línea CR con CR embebidos en campos.

Codificación mixta: la mayoría de los campos vienen en cp1252, pero algunos traen
secuencias UTF-8 (`P\xc3\x81` = "PÁ"). Se parsea el CSV como latin-1 (biyección
byte ↔ carácter, y los separadores son ASCII) y se decodifica cada campo: UTF-8 si
es válido, si no cp1252, y los 5 bytes que cp1252 no define pasan como latin-1.
"""

from __future__ import annotations

import codecs
import csv
import io
import zipfile
from collections.abc import Iterator
from pathlib import Path

import httpx

BULK_BASE = "https://transparenciachc.blob.core.windows.net/lic-da/"
NULLS = ("NA", "")


def _latin1_fallback(exc: UnicodeDecodeError) -> tuple[str, int]:
    return exc.object[exc.start : exc.end].decode("latin-1"), exc.end


codecs.register_error("observatorio_latin1", _latin1_fallback)


def decode_field(value: str) -> str:
    """Recibe un campo leído como latin-1 y devuelve el texto correcto."""
    if value.isascii():
        return value
    raw = value.encode("latin-1")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("cp1252", errors="observatorio_latin1")


def month_key(year: int, month: int) -> str:
    """Clave de mes como la publica ChileCompra: AAAA-M sin cero a la izquierda."""
    return f"{year}-{month}"


def parse_month(value: str) -> tuple[int, int]:
    year, _, month = value.partition("-")
    y, m = int(year), int(month)
    if not 1 <= m <= 12:
        raise ValueError(f"mes inválido: {value!r}")
    return y, m


def months_between(start: str, end: str) -> list[str]:
    y, m = parse_month(start)
    y_end, m_end = parse_month(end)
    out = []
    while (y, m) <= (y_end, m_end):
        out.append(month_key(y, m))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def remote_version(month: str, client: httpx.Client | None = None) -> str | None:
    """Last-Modified del zip remoto, o None si no existe."""
    http = client or httpx.Client(timeout=60)
    try:
        resp = http.head(f"{BULK_BASE}{month}.zip", follow_redirects=True)
    finally:
        if client is None:
            http.close()
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.headers.get("last-modified")


def download(month: str, target_dir: Path, client: httpx.Client | None = None) -> Path:
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"lic_{month}.zip"
    partial = target.with_suffix(".zip.part")
    http = client or httpx.Client(timeout=600)
    try:
        with http.stream("GET", f"{BULK_BASE}{month}.zip", follow_redirects=True) as resp:
            resp.raise_for_status()
            with partial.open("wb") as fh:
                for chunk in resp.iter_bytes():
                    fh.write(chunk)
    finally:
        if client is None:
            http.close()
    partial.replace(target)
    return target


def read_rows(zip_path: Path) -> Iterator[dict[str, str | None]]:
    """Filas del CSV como dict columna → texto, con 'NA'/'' convertidos a None."""
    with zipfile.ZipFile(zip_path) as z:
        names = [n for n in z.namelist() if n.lower().endswith(".csv")]
        if len(names) != 1:
            raise ValueError(f"{zip_path.name}: se esperaba un CSV, hay {names}")
        with z.open(names[0]) as raw:
            yield from read_csv(io.TextIOWrapper(raw, encoding="latin-1", newline=""))


def read_csv(text: io.TextIOBase) -> Iterator[dict[str, str | None]]:
    """`text` debe estar abierto como latin-1 con newline=''."""
    reader = csv.reader(text, delimiter=";")
    header = [decode_field(col) for col in next(reader)]
    for values in reader:
        if len(values) != len(header):
            raise ValueError(f"fila con {len(values)} columnas, cabecera con {len(header)}")
        yield {col: (None if val in NULLS else decode_field(val)) for col, val in zip(header, values, strict=True)}
