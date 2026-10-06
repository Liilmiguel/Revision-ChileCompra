"""Licitaciones en curso: abiertas (API) y cerradas en evaluación (descarga masiva).

No usa la base de datos: corre en una sesión limpia y produce data/vivo/vivo.json, que
la versión web cruza con el historial (plazos típicos, organismos, proveedores).

- Abiertas: la descarga masiva no trae licitaciones publicadas (solo las que ya cerraron),
  así que salen del listado `estado=activas` de la API más el detalle de cada una. El
  detalle cuesta ~2,5 s por licitación (límite de la API), así que se guarda en una caché
  y cada corrida pide solo las nuevas, primero las que cierran antes, hasta `max_detalles`.
  De la API se guardan solo datos de la licitación, nunca nombres de funcionarios.
- En evaluación: licitaciones cerradas aún sin adjudicar en los últimos meses de la
  descarga masiva, con sus ofertas. Aquí las ofertas ya son públicas (tras la apertura).

Oferta anormalmente baja: su total está bajo 30 % de la mediana de las demás ofertas del
mismo alcance (ver analizar_ofertas). Puede anticipar incumplimiento, una oferta "de
cobertura" o un error; en cualquier caso merece revisión antes de adjudicar.
"""

from __future__ import annotations

import json
import logging
import statistics
from collections import defaultdict
from datetime import UTC, date, datetime
from pathlib import Path

import httpx

from observatorio import bulk
from observatorio.api_client import ApiError, MercadoPublicoClient

log = logging.getLogger(__name__)

ESTADOS_EVALUACION = {"6", "11", "12", "13", "14"}  # Cerrada (en evaluación)
# Oferta anormalmente baja: total bajo 30 % de la mediana de las demás del mismo alcance.
# Bajo 5 % casi siempre es un error de digitación o un precio simbólico ($1): se separa.
UMBRAL_BAJA = 0.3
POSIBLE_ERROR = 0.05
PRECIO_UNITARIO = 0.1


def _num(v: str | None) -> float | None:
    if v is None:
        return None
    try:
        return float(v.replace(",", "."))
    except ValueError:
        return None


def _fecha(v: str | None) -> str | None:
    return v[:10] if v and v[:4].isdigit() and not v.startswith("1900") else None


# ---------------------------------------------------------------- abiertas (API)


def resumen_detalle(d: dict) -> dict:
    """Campos de la licitación que usa el análisis; sin datos de funcionarios."""
    c = d.get("Comprador") or {}
    f = d.get("Fechas") or {}
    return {
        "codigo": d["CodigoExterno"],
        "nombre": d.get("Nombre"),
        "estado": str(d.get("CodigoEstado")),
        "tipo": d.get("Tipo"),
        "org": c.get("CodigoOrganismo"),
        "org_nombre": c.get("NombreOrganismo"),
        "region": (c.get("RegionUnidad") or "").strip() or None,
        "publicada": _fecha(f.get("FechaPublicacion")),
        "cierre": (f.get("FechaCierre") or "")[:16] or None,
        "estimado": d.get("MontoEstimado"),
        "moneda": d.get("Moneda"),
        "n_items": (d.get("Items") or {}).get("Cantidad"),
    }


def actualizar_abiertas(
    client: MercadoPublicoClient, cache: dict, max_detalles: int, guardar=lambda: None
) -> tuple[list[dict], dict]:
    """Devuelve (abiertas, estadísticas). Completa la caché con hasta `max_detalles` detalles,
    llamando a `guardar()` cada 100 para no perder lo descargado si el proceso se corta."""
    activas = client.activas()
    # Primero las que cierran antes; las sin fecha de cierre (publicadas hace años y nunca
    # cerradas) al final.
    pendientes = sorted(
        (a for a in activas if a["CodigoExterno"] not in cache),
        key=lambda a: (not a.get("FechaCierre"), a.get("FechaCierre") or ""),
    )
    pedidos = 0
    for a in pendientes[:max_detalles]:
        try:
            d = client.detail(a["CodigoExterno"])
        except ApiError as exc:
            log.warning("detalle %s: %s", a["CodigoExterno"], client.mask(str(exc)))
            continue
        pedidos += 1
        if d:
            cache[a["CodigoExterno"]] = resumen_detalle(d)
        if pedidos % 100 == 0:
            guardar()
            log.info("%d detalles nuevos", pedidos)
    abiertas = []
    for a in activas:
        r = dict(cache.get(a["CodigoExterno"]) or {"codigo": a["CodigoExterno"], "nombre": a.get("Nombre")})
        r["cierre"] = (a.get("FechaCierre") or r.get("cierre") or "")[:16] or None
        r["con_detalle"] = a["CodigoExterno"] in cache
        abiertas.append(r)
    stats = {"activas": len(activas), "con_detalle": sum(r["con_detalle"] for r in abiertas), "pedidos": pedidos}
    return abiertas, stats


# ---------------------------------------------------------------- en evaluación (masiva)


def analizar_ofertas(filas: list[dict], estimado: float | None = None) -> list[dict]:
    """Ofertas por proveedor de una licitación, con la marca de oferta anormalmente baja.

    Se comparan totales ofertados entre proveedores del mismo alcance (mismo número de líneas
    ofertadas), con al menos 3 en el grupo. La comparación por línea se descartó: las
    diferencias de unidad (caja vs unidad) marcaban 21 % de las licitaciones. Se omiten las
    licitaciones adjudicadas por precio unitario (mediana de los totales < 10 % del estimado)."""
    prov: dict[str, dict] = {}
    for r in filas:
        p = r.get("CodigoProveedor")
        if not p:
            continue
        e = prov.setdefault(
            p,
            {
                "prov": p,
                "nombre": r.get("NombreProveedor"),
                "rut": r.get("RutProveedor"),
                "total": 0.0,
                "lineas": 0,
                "rechazada": False,
            },
        )
        e["total"] += _num(r.get("Valor Total Ofertado")) or 0.0
        e["lineas"] += 1
        e["rechazada"] |= r.get("Estado Oferta") == "Rechazada"
    grupos: dict[int, list[dict]] = defaultdict(list)
    for e in prov.values():
        e["razon_pares"] = None
        e["clase"] = None
        if e["total"] > 0:
            grupos[e["lineas"]].append(e)
    for grupo in grupos.values():
        if len(grupo) < 3:
            continue
        for e in grupo:
            med = statistics.median(x["total"] for x in grupo if x is not e)
            if estimado and med < PRECIO_UNITARIO * estimado:
                continue
            e["razon_pares"] = round(e["total"] / med, 4)
            if e["razon_pares"] < POSIBLE_ERROR:
                e["clase"] = "posible_error"
            elif e["razon_pares"] < UMBRAL_BAJA:
                e["clase"] = "muy_baja"
    return sorted(prov.values(), key=lambda e: e["total"])


def en_evaluacion(zips: list[Path]) -> list[dict]:
    """Licitaciones cerradas sin adjudicar en los zips de la descarga masiva."""
    lics: dict[str, dict] = {}
    filas: dict[str, list[dict]] = defaultdict(list)
    for z in zips:
        for row in bulk.read_rows(z):
            if row.get("CodigoEstado") not in ESTADOS_EVALUACION:
                continue
            c = row["CodigoExterno"]
            if c not in lics:
                lics[c] = {
                    "codigo": c,
                    "nombre": row.get("Nombre"),
                    "estado": row.get("CodigoEstado"),
                    "tipo": row.get("Tipo"),
                    "org": row.get("CodigoOrganismo"),
                    "org_nombre": row.get("NombreOrganismo"),
                    "region": (row.get("RegionUnidad") or "").strip() or None,
                    "publicada": _fecha(row.get("FechaPublicacion")),
                    "cierre": _fecha(row.get("FechaCierre")),
                    "adjudicacion_estimada": _fecha(row.get("FechaAdjudicacion")),
                    "estimado": _num(row.get("MontoEstimado")) or None,
                    "moneda": row.get("CodigoMoneda"),
                }
            filas[c].append(row)
    for c, lic in lics.items():
        lic["ofertas"] = analizar_ofertas(filas[c], lic["estimado"])
    return list(lics.values())


# Orden de los campos de cada oferta en vivo.json (arreglos: ~40 mil ofertas).
CAMPOS_OFERTA = ["prov", "total", "lineas", "rechazada", "razon_pares", "clase"]


def compactar(evaluacion: list[dict]) -> tuple[list[dict], dict[str, list]]:
    """Ofertas como arreglos y nombre/RUT de cada proveedor una sola vez."""
    proveedores: dict[str, list] = {}
    out = []
    for lic in evaluacion:
        ofertas = []
        for o in lic["ofertas"]:
            proveedores.setdefault(o["prov"], [o["nombre"], o["rut"]])
            ofertas.append(
                [o["prov"], round(o["total"], 2), o["lineas"], int(o["rechazada"]), o["razon_pares"], o["clase"]]
            )
        out.append({**lic, "ofertas": ofertas})
    return out, proveedores


def meses_recientes(hoy: date, n: int) -> list[str]:
    y, m = hoy.year, hoy.month
    out = []
    for _ in range(n):
        out.append(bulk.month_key(y, m))
        y, m = (y - 1, 12) if m == 1 else (y, m - 1)
    return out[::-1]


def generar(
    out_dir: Path,
    raw_dir: Path,
    ticket: str | None,
    max_detalles: int,
    meses: int = 4,
    semilla: Path | None = None,
) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    cache_path = out_dir / "api_cache.json"
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    # En una sesión limpia no hay caché: se reconstruye desde el vivo.json publicado antes.
    if semilla and semilla.exists():
        for r in json.loads(semilla.read_text()).get("abiertas", []):
            if r.pop("con_detalle", False):
                cache.setdefault(r["codigo"], r)

    fuentes: dict = {"masiva": {}}
    zips = []
    with httpx.Client(timeout=600) as http:
        for mes in meses_recientes(date.today(), meses):
            version = bulk.remote_version(mes, http)
            if version is None:
                continue
            zips.append(bulk.download(mes, raw_dir, http))
            fuentes["masiva"][mes] = version
    evaluacion, proveedores = compactar(en_evaluacion(zips))

    abiertas: list[dict] = []
    if ticket:
        with MercadoPublicoClient(ticket) as client:
            abiertas, fuentes["api"] = actualizar_abiertas(
                client, cache, max_detalles, lambda: cache_path.write_text(json.dumps(cache, ensure_ascii=False))
            )
        # La caché solo guarda licitaciones aún activas.
        activas = {a["codigo"] for a in abiertas}
        cache = {k: v for k, v in cache.items() if k in activas}
        cache_path.write_text(json.dumps(cache, ensure_ascii=False))
    else:
        fuentes["api"] = None

    resultado = {
        "generado": datetime.now(UTC).isoformat(timespec="minutes"),
        "fuentes": fuentes,
        "abiertas": abiertas,
        "campos_oferta": CAMPOS_OFERTA,
        "evaluacion": evaluacion,
        "proveedores": proveedores,
    }
    (out_dir / "vivo.json").write_text(
        json.dumps(resultado, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    )
    return {"abiertas": len(abiertas), "evaluacion": len(evaluacion), **(fuentes.get("api") or {})}
