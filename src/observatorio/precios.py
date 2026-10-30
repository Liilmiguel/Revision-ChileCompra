"""Precios unitarios en órdenes de compra: comparación entre compras del mismo producto.

Usa todas las líneas en pesos de la descarga masiva de órdenes de compra (12 meses): las de
licitación (SE), convenio marco (CM), Compra Ágil (AG) y trato directo (TD). Las de SE y CM
sirven de referencia; se marcan solo las compras directas (AG y TD).

"Mismo producto" = mismo código ONU, misma unidad y mismas primeras 6 palabras de la
especificación del comprador (sin tildes ni signos). Es estricto a propósito: con el código
ONU solo, Trikafta y pancreatina quedaban juntos (el comprador eligió mal el código). Las
líneas de convenio marco traen el código del catálogo al inicio de la especificación, así que
ahí la clave es casi exacta.

Tres comparaciones:
- sobre la mediana: compra directa con precio unitario 3+ veces la mediana del mismo producto
  (grupo con 5+ líneas de 2+ organismos). Exceso = (precio − mediana) × cantidad.
- mismo proveedor, precios distintos: el mismo proveedor vende el mismo producto a precios
  que difieren 1,5+ veces en el año. Exceso = (precio − mínimo) × cantidad.
- sin precio unitario: orden de compra directa de bienes sobre 1.000 UTM cuyas líneas son todas
  "1 Unidad no definida" o "Global", o con una línea de cantidad 1 a 100+ veces la mediana
  del producto (un contrato completo cargado como un ítem): el precio no se puede verificar.

Solo bienes (no servicios ni unidades como "mes" o "global"), y razones hasta 50 veces: más
allá son casi siempre errores de unidad (caja contra unidad, litro contra camión).
"""

from __future__ import annotations

import json
import logging
import re
import statistics
import unicodedata
from collections import defaultdict
from datetime import UTC, date, datetime
from pathlib import Path

import httpx

from observatorio import bulk, compras

log = logging.getLogger(__name__)

PALABRAS = 10  # con 6, los frascos de 4 ml y 10 ml de nivolumab quedaban como el mismo producto
MIN_LINEAS = 5
MIN_ORGS = 2
RAZON_ALTA = 3.0
RAZON_PROVEEDOR = 1.5
EXCESO_MIN = 1_000_000  # pesos: casos menores no se listan
OPACA_UTM = 1000
UNIDADES_OPACAS = {"", "UNIDAD NO DEFINIDA", "GLOBAL"}
MAX_LISTA = 5000
# Solo bienes: en servicios la "unidad" (mes, global, hora…) describe un alcance, no una cantidad
# comparable, y la primera versión los llenaba de falsos casos (guardias "por mes" a 17 veces
# la mediana). Segmentos UNSPSC 70–95 = servicios.
UNIDADES_NO_FISICAS = UNIDADES_OPACAS | {
    "MES", "HORA HOMBRE", "HORA", "DIA", "DIAS", "SEMANA", "ANO", "SERVICIO", "SESION", "JORNADA", "VIAJE",
    "EVENTO", "CURSO", "TURNO", "MINUTO", "PERSONA", "PROYECTO", "ESTUDIO", "INFORME", "VISITA",
}  # fmt: skip
# Una línea con cantidad 1 y precio 100+ veces la mediana es un contrato completo cargado como
# un ítem (pembrolizumab a $57 mil millones, "diésel litro" a $156 millones): no es sobreprecio
# sino falta de precio unitario. Razones sobre RAZON_MAX son casi siempre errores de unidad.
RAZON_LINEA_OPACA = 100
# Descripciones que no identifican un bien: servicios con código de bien ("servicio de arriendo de
# carpa") y glosas genéricas que juntan productos distintos ("insumos cirugía según detalle").
GENERICAS = re.compile(
    r"\b(SERVICIOS?|ARRIENDO|MANTENCION|MANTENIMIENTO|REPARACION|RETIRO|INSTALACION|SEGUN|DETALLE|VARIOS|OTROS"
    r"|ADJUNTO|CONTINUIDAD|INSUMOS|MATERIALES)\b"
)
RAZON_MAX = 50


def normalizar(texto: str | None) -> str:
    t = unicodedata.normalize("NFD", (texto or "").upper())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"[^A-Z0-9]+", " ", t).strip()


def es_servicio(onu: str | None) -> bool:
    return bool(onu) and len(onu) >= 2 and onu[:2].isdigit() and 70 <= int(onu[:2]) <= 95


def clave(onu: str | None, unidad: str | None, espec: str | None) -> tuple[str, str, str] | None:
    """Clave de "mismo producto", o None si la línea no es un bien comparable."""
    u = normalizar(unidad)
    palabras = normalizar(espec).split()[:PALABRAS]
    if not palabras or es_servicio(onu) or GENERICAS.search(" ".join(palabras)):
        return None
    # Convenio marco: sin unidad, pero la especificación parte con el código del catálogo,
    # que identifica el producto exacto. Son las mejores referencias de precio.
    if u == "" and palabras[0].isdigit():
        u = "CATALOGO"
    if u in UNIDADES_NO_FISICAS:
        return None
    return (onu or "", u, " ".join(palabras))


def _num(v: str | None) -> float | None:
    if not v:
        return None
    try:
        return float(v.replace(",", "."))
    except ValueError:
        return None


def leer_lineas(zip_path: Path, lineas: list, ocs: dict) -> None:
    """Agrega a `lineas` las líneas en pesos con precio y cantidad, y a `ocs` la cabecera
    de cada orden de compra (tipo, fecha, organismo, proveedor, monto)."""
    for r in bulk.read_rows(zip_path):
        c = r.get("Codigo")
        estado = r.get("Estado") or ""
        if not c or "ancel" in estado or "limin" in estado:
            continue
        tipo = "AG" if r.get("EsCompraAgil") == "Si" else "TD" if r.get("EsTratoDirecto") == "Si" else r.get("Tipo")
        if c not in ocs:
            ocs[c] = {
                "tipo": tipo,
                "fecha": (r.get("FechaEnvio") or r.get("FechaCreacion") or "")[:10],
                "org": r.get("CodigoOrganismoPublico"),
                "prov": r.get("CodigoProveedor"),
                "prov_nombre": r.get("NombreProveedor"),
                "prov_rut": r.get("RutSucursal"),
                "monto": _num(r.get("MontoTotalOC_PesosChilenos")) or 0.0,
                "opaca": True,  # se desmiente con cualquier línea con precio unitario verificable
                "bien": False,  # en servicios una línea "global" es normal: solo se marcan bienes
                "producto": None,
            }
        oc = ocs[c]
        q, p = _num(r.get("cantidad")), _num(r.get("precioNeto"))
        unidad = normalizar(r.get("UnidadMedida"))
        if not (q == 1 and unidad in UNIDADES_OPACAS):
            oc["opaca"] = False
        if not es_servicio(r.get("codigoProductoONU")):
            oc["bien"] = True
        if oc["producto"] is None:
            oc["producto"] = (r.get("EspecificacionComprador") or r.get("NombreroductoGenerico") or "")[:120]
        if r.get("monedaItem") != "CLP" or not p or not q or p <= 0 or q <= 0:
            continue
        k = clave(r.get("codigoProductoONU"), r.get("UnidadMedida"), r.get("EspecificacionComprador"))
        if k is None:
            continue
        lineas.append((k, p, q, c))


def analizar(lineas: list, ocs: dict, utm: float = compras.UTM_CLP) -> dict:
    grupos: dict[tuple, list] = defaultdict(list)
    for k, p, q, c in lineas:
        grupos[k].append((p, q, c))

    sobre, mismo = [], []
    exceso_prov: dict[str, list] = defaultdict(lambda: [0.0, 0])
    comparables = 0
    for k, xs in grupos.items():
        med = statistics.median(p for p, _, _ in xs)
        if len(xs) >= 3:
            normales = []
            for p, q, c in xs:
                if q <= 1 and p > RAZON_LINEA_OPACA * med:
                    ocs[c]["opaca"] = True
                else:
                    normales.append((p, q, c))
            xs = normales
            med = statistics.median(p for p, _, _ in xs)
        orgs = {ocs[c]["org"] for _, _, c in xs}
        if len(xs) >= MIN_LINEAS and len(orgs) >= MIN_ORGS:
            comparables += len(xs)
            for p, q, c in xs:
                oc = ocs[c]
                if oc["tipo"] not in ("AG", "TD") or not RAZON_ALTA * med <= p <= RAZON_MAX * med:
                    continue
                exceso = (p - med) * q
                if exceso < EXCESO_MIN:
                    continue
                fila = [c, oc["fecha"], oc["tipo"], oc["org"], oc["prov"], k[2], k[0], k[1], q]
                sobre.append([*fila, round(p), round(med), round(p / med, 1), len(xs), round(exceso)])
                e = exceso_prov[oc["prov"]]
                e[0] += exceso
                e[1] += 1
        # Mismo proveedor, mismo producto, precios distintos (compras directas).
        por_prov: dict[str, list] = defaultdict(list)
        for p, q, c in xs:
            if ocs[c]["tipo"] in ("AG", "TD"):
                por_prov[ocs[c]["prov"]].append((p, q, c))
        for prov, ys in por_prov.items():
            if len({c for _, _, c in ys}) < 2:
                continue
            pmin = min(p for p, _, _ in ys)
            pmax = max(p for p, _, _ in ys)
            if not RAZON_PROVEEDOR * pmin <= pmax <= RAZON_MAX * pmin:
                continue
            exceso = sum((p - pmin) * q for p, q, _ in ys)
            if exceso < EXCESO_MIN:
                continue
            caras = sorted(ys, key=lambda y: -y[0])
            mismo.append([prov, k[2], k[0], k[1], len({c for _, _, c in ys}), round(pmin), round(pmax),
                          round(pmax / pmin, 1), round(exceso), sorted({ocs[c]["org"] for _, _, c in ys}),
                          [c for _, _, c in caras][:20]])  # fmt: skip

    opacas = sorted(
        (
            [c, o["fecha"], o["tipo"], o["org"], o["prov"], round(o["monto"]), o["producto"]]
            for c, o in ocs.items()
            if o["opaca"] and o.get("bien", True) and o["tipo"] in ("AG", "TD") and o["monto"] > OPACA_UTM * utm
        ),
        key=lambda x: -x[5],
    )
    sobre.sort(key=lambda x: -x[-1])
    mismo.sort(key=lambda x: -x[8])
    return {
        "resumen": {
            "lineas": len(lineas),
            "productos": len(grupos),
            "lineas_comparables": comparables,
            "sobre_n": len(sobre),
            "sobre_exceso": round(sum(x[-1] for x in sobre)),
            "mismo_n": len(mismo),
            "mismo_exceso": round(sum(x[8] for x in mismo)),
            "opacas_n": len(opacas),
            "opacas_monto": sum(x[5] for x in opacas),
        },
        "campos_sobre": [
            "oc",
            "fecha",
            "tipo",
            "org",
            "prov",
            "producto",
            "onu",
            "unidad",
            "cantidad",
            "precio",
            "mediana",
            "razon",
            "n_ref",
            "exceso",
        ],  # fmt: skip
        "sobre_mediana": sobre[:MAX_LISTA],
        "campos_mismo": [
            "prov",
            "producto",
            "onu",
            "unidad",
            "n_oc",
            "p_min",
            "p_max",
            "razon",
            "exceso",
            "orgs",
            "ocs",
        ],  # fmt: skip
        "mismo_proveedor": mismo[:MAX_LISTA],
        "campos_opacas": ["oc", "fecha", "tipo", "org", "prov", "monto", "producto"],
        "sin_precio_unitario": opacas[:MAX_LISTA],
        # Exceso sobre la mediana por proveedor (todas, no solo las listadas): pestaña Proveedores.
        "exceso_proveedor": {p: [round(e), n] for p, (e, n) in exceso_prov.items()},
    }


def generar(out_dir: Path, raw_dir: Path, meses: int = 12) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    lineas: list = []
    ocs: dict = {}
    fuentes = {}
    with httpx.Client(timeout=900) as http:
        for mes in compras.meses_cerrados(date.today(), meses):
            version = bulk.remote_version(mes, http, base=compras.OC_BASE)
            if version is None:
                continue
            z = raw_dir / f"oc_{mes}.zip"
            if not z.exists():
                z = bulk.download(mes, raw_dir, http, base=compras.OC_BASE, prefijo="oc")
            antes = len(lineas)
            leer_lineas(z, lineas, ocs)
            log.info("%s: %d líneas", mes, len(lineas) - antes)
            fuentes[mes] = version
    resultado = {
        "generado": datetime.now(UTC).isoformat(timespec="minutes"),
        "fuentes": fuentes,
        "constantes": {
            "PALABRAS": PALABRAS,
            "MIN_LINEAS": MIN_LINEAS,
            "MIN_ORGS": MIN_ORGS,
            "RAZON_ALTA": RAZON_ALTA,
            "RAZON_PROVEEDOR": RAZON_PROVEEDOR,
            "EXCESO_MIN": EXCESO_MIN,
            "OPACA_UTM": OPACA_UTM,
            "RAZON_MAX": RAZON_MAX,
            "RAZON_LINEA_OPACA": RAZON_LINEA_OPACA,
        },  # fmt: skip
        **analizar(lineas, ocs),
    }
    # Nombre y RUT de los proveedores citados (los organismos salen de compras.json).
    citados = {x[4] for x in resultado["sobre_mediana"]} | {x[0] for x in resultado["mismo_proveedor"]}
    citados |= {x[4] for x in resultado["sin_precio_unitario"]}
    resultado["proveedores"] = {}
    for o in ocs.values():
        if o["prov"] in citados and o["prov"] not in resultado["proveedores"]:
            resultado["proveedores"][o["prov"]] = [o.get("prov_nombre"), o.get("prov_rut")]
    (out_dir / "precios.json").write_text(json.dumps(resultado, ensure_ascii=False, separators=(",", ":")))
    return resultado["resumen"]
