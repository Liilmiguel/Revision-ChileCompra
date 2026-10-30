"""Participaciones en sociedades declaradas en InfoProbidad, desde los catálogos de datos abiertos
del Consejo para la Transparencia (datos.cplt.cl, licencia CC BY 4.0).

- csvdeclaraciones: una fila por declaración (declarante, institución, cargo, fecha, tipo).
- csvaccionDerecho: acciones y derechos en sociedades de cada declaración (RUT sin dígito
  verificador, nombre, cantidad, país).

Se usa la última declaración de cada declarante (por su URI, estable entre declaraciones). El
catálogo no trae el enlace a la ficha en infoprobidad.cl ni las participaciones del cónyuge: se
toman de una extracción anterior de las fichas cuando coinciden nombre y fecha de la declaración.

La salida tiene el esquema que espera `conflictos`.
"""

from __future__ import annotations

import csv
import json
import logging
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import httpx

from observatorio.precios import normalizar

log = logging.getLogger(__name__)

BASE = "https://datos.cplt.cl/catalogos/infoprobidad"
CATALOGOS = {"declaraciones": "csvdeclaraciones", "acciones": "csvaccionDerecho"}
FUENTE = "InfoProbidad, catálogos de datos abiertos del CPLT (datos.cplt.cl), licencia CC BY 4.0"


def descargar(destino: Path, client: httpx.Client) -> dict[str, Path]:
    destino.mkdir(parents=True, exist_ok=True)
    rutas = {}
    for nombre, recurso in CATALOGOS.items():
        ruta = destino / f"{recurso}.csv"
        with client.stream("GET", f"{BASE}/{recurso}", timeout=900) as r:
            r.raise_for_status()
            with ruta.open("wb") as f:
                for chunk in r.iter_bytes():
                    f.write(chunk)
        log.info("%s: %.1f MB", recurso, ruta.stat().st_size / 1e6)
        rutas[nombre] = ruta
    return rutas


def dv(cuerpo: int) -> str:
    """Dígito verificador del RUT (módulo 11)."""
    s, m = 0, 2
    for d in reversed(str(cuerpo)):
        s += int(d) * m
        m = 2 if m == 7 else m + 1
    r = 11 - s % 11
    return {11: "0", 10: "K"}.get(r, str(r))


def rut_sociedad(valor: str | None) -> str | None:
    try:
        cuerpo = int(float(valor or ""))
    except ValueError:
        return None
    return f"{cuerpo}-{dv(cuerpo)}" if cuerpo > 1_000_000 else None


def _leer(ruta: Path) -> list[dict]:
    with ruta.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def leer_fichas(extraccion: Path | None) -> list[dict]:
    """Filas de una extracción de las fichas de infoprobidad.cl (ver participaciones())."""
    if not extraccion or not extraccion.exists():
        return []
    datos = json.loads(extraccion.read_text())
    return datos["filas"] if isinstance(datos, dict) else datos


def participaciones(declaraciones: list[dict], acciones: list[dict], fichas: list[dict] | None = None) -> dict:
    """Participaciones de la última declaración de cada declarante. De `fichas` se toman el enlace
    a la declaración y las filas de otros titulares (cónyuge, hijos) de esa misma declaración."""
    fichas = fichas or []
    clave = lambda nombre, fecha: (normalizar(nombre), fecha)  # noqa: E731
    urls = {clave(f.get("declarante_nombre"), f.get("fecha_declaracion")): f.get("url_declaracion") for f in fichas}
    ultima: dict[str, dict] = {}
    for d in declaraciones:
        k = d["UriDeclarante"]
        if k not in ultima or (d["Declaracion"], d["UriDeclaracion"]) > (
            ultima[k]["Declaracion"],
            ultima[k]["UriDeclaracion"],
        ):
            ultima[k] = d
    por_uri = {d["UriDeclaracion"]: d for d in ultima.values()}
    filas, sin_rut = [], 0
    for a in acciones:
        d = por_uri.get(a["UriDeclaracion"])
        if d is None:
            continue
        rut = rut_sociedad(a.get("RutJuridica"))
        if rut is None:
            sin_rut += 1
            continue
        nombre = " ".join(x for x in (d["Nombre"], d["ApPaterno"], d["ApMaterno"]) if x).strip()
        fecha = d["Declaracion"][:10]
        pais = (a.get("Pais") or "").strip()
        filas.append(
            {
                "rut_sociedad": rut,
                "nombre_sociedad": (a.get("EntidadAccion") or "").strip(),
                "tipo": None,
                "porcentaje": None,
                "cantidad_o_porcentaje_declarado": a.get("Cantidad"),
                "extranjera": bool(pais) and pais != "CHILE",
                "controlador": a.get("Controlador") == "1",
                "titular": "declarante",
                "declarante_id": d["UriDeclarante"].rsplit("/", 1)[-1],
                "declarante_nombre": nombre,
                "cargo": d["Cargo"],
                "servicio": d["Institucion"],
                "tipo_declaracion": d["Tipo"],
                "fecha_declaracion": fecha,
                "url_declaracion": urls.get(clave(nombre, fecha)),
            }
        )
    vigentes = {clave(f["declarante_nombre"], f["fecha_declaracion"]) for f in filas}
    vigentes |= {
        clave(" ".join(x for x in (d["Nombre"], d["ApPaterno"], d["ApMaterno"]) if x), d["Declaracion"][:10])
        for d in ultima.values()
    }
    otros = [
        f
        for f in fichas
        if f.get("titular") not in (None, "declarante")
        and clave(f.get("declarante_nombre"), f.get("fecha_declaracion")) in vigentes
    ]
    filas += otros
    return {
        "generado": datetime.now(UTC).isoformat(timespec="minutes"),
        "fuente": FUENTE,
        "declaraciones": len(ultima),
        "cobertura": {
            "completa": True,
            "declarantes_objetivo": len(ultima),
            "declarantes_consultados": len(ultima),
            "fecha_ultima_declaracion": max((d["Declaracion"][:10] for d in ultima.values()), default=None),
            "nota": "Última declaración de cada declarante según los catálogos de datos abiertos del CPLT. "
            "Las participaciones del cónyuge vienen de la extracción de fichas, si la hay.",
        },
        "descartadas_sin_rut": sin_rut,
        "de_otros_titulares": len(otros),
        "filas": filas,
    }


def generar(destino: Path, extraccion: Path | None = None) -> dict:
    with httpx.Client(follow_redirects=True) as client:
        rutas = descargar(destino / "catalogos", client)
    r = participaciones(_leer(rutas["declaraciones"]), _leer(rutas["acciones"]), leer_fichas(extraccion))
    (destino / "participaciones.json").write_text(json.dumps(r, ensure_ascii=False, separators=(",", ":")))
    con_url = sum(1 for f in r["filas"] if f["url_declaracion"])
    return {
        "declarantes": r["declaraciones"],
        "filas": len(r["filas"]),
        "con_enlace": con_url,
        "sin_rut": r["descartadas_sin_rut"],
        "de_otros_titulares": r["de_otros_titulares"],
        "ultima_declaracion": r["cobertura"]["fecha_ultima_declaracion"],
        "sociedades": len(Counter(f["rut_sociedad"] for f in r["filas"])),
    }
