"""Compras Ágiles y tratos directos: órdenes de compra sin licitación pública.

Fuente: descarga masiva de órdenes de compra (oc-da), un zip mensual de ~100 MB con una
fila por ítem. No usa la base de datos: agrega por orden de compra y escribe
data/compras/compras.json para la versión web.

- Compra Ágil: compras de hasta 100 UTM con impuestos, por cotización simple. El tope se
  mide en los datos: en septiembre de 2026 no hay ninguna sobre ~$7,2 millones (100 UTM
  de ~$72.000) y la cantidad crece de forma marcada entre 90 y 100 UTM.
- Trato directo: contratación sin concurso, con una causal legal (proveedor único,
  emergencia, etc.).

Señales (pistas para revisar, no pruebas):
- fraccionamiento: 3+ Compras Ágiles del mismo organismo al mismo proveedor y rubro en 30
  días que juntas superan el tope; es la forma de eludir una licitación dividiendo la compra.
- bajo el tope: Compra Ágil entre 90 % y 100 % del tope del mes. Una por sí sola no dice
  nada; un organismo con el doble de la proporción nacional sí.
- trato directo recurrente: 5+ tratos directos del mismo organismo al mismo proveedor.
- trato directo de monto alto: sobre 1.000 UTM.
"""

from __future__ import annotations

import json
import logging
from collections import Counter, defaultdict
from datetime import UTC, date, datetime
from pathlib import Path

import httpx

from observatorio import bulk

log = logging.getLogger(__name__)

OC_BASE = "https://transparenciachc.blob.core.windows.net/oc-da/"
UTM_CLP = 72000  # aproximado 2025–2026; solo para el umbral de 1.000 UTM de tratos directos
BANDA_TOPE = 0.9
FRACC_DIAS = 30
FRACC_MIN = 3
TD_RECURRENTE = 5
TD_ALTO_UTM = 1000
MAX_LISTA = 10000  # casos por lista en compras.json (los de mayor monto); hoy caben todos


def _num(v: str | None) -> float:
    if not v:
        return 0.0
    try:
        return float(v.replace(",", "."))
    except ValueError:
        return 0.0


def leer_mes(zip_path: Path) -> list[dict]:
    """Compras Ágiles y tratos directos del mes, una entrada por orden de compra.

    El archivo trae una fila por ítem: la cabecera sale de la primera fila y el rubro del
    ítem de mayor monto. Se omiten las órdenes canceladas o eliminadas."""
    ocs: dict[str, dict] = {}
    linea_max: dict[str, float] = {}
    for r in bulk.read_rows(zip_path):
        c = r.get("Codigo")
        if not c:
            continue
        oc = ocs.get(c)
        if oc is None:
            ag, td = r.get("EsCompraAgil") == "Si", r.get("EsTratoDirecto") == "Si"
            estado = r.get("Estado") or ""
            if not (ag or td) or "ancel" in estado or "limin" in estado:
                ocs[c] = {}  # se recuerda para no volver a evaluarla
                continue
            oc = ocs[c] = {
                "codigo": c,
                "fecha": (r.get("FechaEnvio") or r.get("FechaCreacion") or "")[:10],
                "tipo": "AG" if ag else "TD",
                "causal": None if ag else r.get("ProcedenciaOC"),
                "org": r.get("CodigoOrganismoPublico"),
                "org_nombre": r.get("OrganismoPublico"),
                "region": (r.get("RegionUnidadCompra") or "").strip() or None,
                "prov": r.get("CodigoProveedor"),
                "prov_nombre": r.get("NombreProveedor"),
                "monto": _num(r.get("MontoTotalOC_PesosChilenos")),
                "rubro": None,
                "rubro2": None,
                "nombre": (r.get("Nombre") or "")[:140],
            }
        if not oc:
            continue
        neto = _num(r.get("totalLineaNeto"))
        if oc["rubro"] is None or neto > linea_max[c]:
            oc["rubro"], oc["rubro2"] = r.get("RubroN1"), r.get("RubroN2")
            linea_max[c] = neto
    return [o for o in ocs.values() if o and o["fecha"] and o["org"] and o["prov"]]


def tope_mes(ags: list[dict]) -> float | None:
    """Tope de Compra Ágil del mes medido en los datos: percentil 99,95 de los montos
    (robusto a una orden mal digitada; el tope real queda a menos de 1 % de este valor)."""
    montos = sorted(o["monto"] for o in ags if o["monto"] > 0)
    if len(montos) < 1000:
        return None
    return montos[int(0.9995 * (len(montos) - 1))]


def fraccionamiento(ags: list[dict], topes: dict[str, float]) -> list[dict]:
    """Episodios: rachas de Compras Ágiles del mismo organismo, proveedor y rubro donde
    alguna ventana de FRACC_DIAS días tiene FRACC_MIN+ órdenes que superan el tope."""
    grupos: dict[tuple, list[dict]] = defaultdict(list)
    for o in ags:
        grupos[(o["org"], o["prov"], o["rubro"])].append(o)
    episodios = []
    for xs in grupos.values():
        if len(xs) < FRACC_MIN:
            continue
        xs.sort(key=lambda o: o["fecha"])
        dias = [date.fromisoformat(o["fecha"]).toordinal() for o in xs]
        marcadas = [False] * len(xs)
        j = 0
        suma = 0.0
        for i in range(len(xs)):
            suma += xs[i]["monto"]
            while dias[i] - dias[j] > FRACC_DIAS:
                suma -= xs[j]["monto"]
                j += 1
            tope = topes.get(xs[i]["fecha"][:7])
            if tope and i - j + 1 >= FRACC_MIN and suma > tope:
                for k in range(j, i + 1):
                    marcadas[k] = True
        # Órdenes marcadas consecutivas (a menos de FRACC_DIAS días) forman un episodio.
        actual: list[dict] = []
        for o, d, m in zip(xs, dias, marcadas, strict=True):
            if m and actual and d - date.fromisoformat(actual[-1]["fecha"]).toordinal() > FRACC_DIAS:
                episodios.append(actual)
                actual = []
            if m:
                actual.append(o)
        if actual:
            episodios.append(actual)
    out = []
    for ep in episodios:
        o0 = ep[0]
        out.append(
            {
                "org": o0["org"],
                "prov": o0["prov"],
                "rubro": o0["rubro"],
                "desde": ep[0]["fecha"],
                "hasta": ep[-1]["fecha"],
                "n": len(ep),
                "monto": round(sum(o["monto"] for o in ep)),
                "codigos": [o["codigo"] for o in ep],
            }
        )
    return sorted(out, key=lambda e: -e["monto"])


def analizar(ocs: list[dict]) -> dict:
    ags = [o for o in ocs if o["tipo"] == "AG"]
    tds = [o for o in ocs if o["tipo"] == "TD"]
    por_mes_ag: dict[str, list[dict]] = defaultdict(list)
    for o in ags:
        por_mes_ag[o["fecha"][:7]].append(o)
    topes = {m: t for m, xs in por_mes_ag.items() if (t := tope_mes(xs))}

    # Compras Ágiles en la banda bajo el tope, e histograma nacional (monto / tope, 2 %).
    hist = [0] * 51
    for o in ags:
        t = topes.get(o["fecha"][:7])
        if not t:
            continue
        r = o["monto"] / t
        o["banda"] = BANDA_TOPE <= r <= 1.0
        hist[min(int(r * 50), 50)] += 1

    episodios = fraccionamiento(ags, topes)
    en_episodio = {c for e in episodios for c in e["codigos"]}
    for e in episodios:
        e["codigos"] = e["codigos"][:50]

    # Por organismo.
    orgs: dict[str, dict] = {}
    for o in ocs:
        e = orgs.setdefault(
            o["org"],
            {
                "nombre": o["org_nombre"],
                "region": o["region"],
                "ag_n": 0,
                "ag_monto": 0.0,
                "ag_banda": 0,
                "td_n": 0,
                "td_monto": 0.0,
                "fracc_n": 0,
            },
        )
        if o["tipo"] == "AG":
            e["ag_n"] += 1
            e["ag_monto"] += o["monto"]
            e["ag_banda"] += bool(o.get("banda"))
            e["fracc_n"] += o["codigo"] in en_episodio
        else:
            e["td_n"] += 1
            e["td_monto"] += o["monto"]

    # Tratos directos recurrentes (organismo × proveedor) y de monto alto.
    pares: dict[tuple, list[dict]] = defaultdict(list)
    for o in tds:
        pares[(o["org"], o["prov"])].append(o)
    recurrentes = []
    for (org, prov), xs in pares.items():
        if len(xs) < TD_RECURRENTE:
            continue
        causal = Counter(o["causal"] for o in xs).most_common(1)[0][0]
        recurrentes.append(
            {
                "org": org,
                "prov": prov,
                "n": len(xs),
                "monto": round(sum(o["monto"] for o in xs)),
                "causal": causal,
                "desde": min(o["fecha"] for o in xs),
                "hasta": max(o["fecha"] for o in xs),
                "rubro": Counter(o["rubro"] for o in xs).most_common(1)[0][0],
                "codigos": [o["codigo"] for o in sorted(xs, key=lambda o: -o["monto"])][:30],
            }
        )
    recurrentes.sort(key=lambda e: -e["monto"])
    altos = sorted(
        (
            {k: o[k] for k in ("codigo", "fecha", "org", "prov", "monto", "causal", "nombre", "rubro")}
            for o in tds
            if o["monto"] > TD_ALTO_UTM * UTM_CLP
        ),
        key=lambda o: -o["monto"],
    )

    episodios, recurrentes, altos = episodios[:MAX_LISTA], recurrentes[:MAX_LISTA], altos[:MAX_LISTA]
    usados = {e["prov"] for lista in (episodios, recurrentes, altos) for e in lista}
    proveedores = {}
    for o in ocs:
        if o["prov"] in usados and o["prov"] not in proveedores:
            proveedores[o["prov"]] = o["prov_nombre"]

    por_mes: dict[str, list] = defaultdict(lambda: [0, 0.0, 0, 0.0])
    for o in ocs:
        m = por_mes[o["fecha"][:7]]
        k = 0 if o["tipo"] == "AG" else 2
        m[k] += 1
        m[k + 1] += o["monto"]
    return {
        "topes": topes,
        "por_mes": [[m, *[round(x) for x in v]] for m, v in sorted(por_mes.items())],
        "hist_ag": hist,
        "organismos": [
            [
                c,
                e["nombre"],
                e["region"],
                e["ag_n"],
                round(e["ag_monto"]),
                e["ag_banda"],
                e["td_n"],
                round(e["td_monto"]),
                e["fracc_n"],
            ]
            for c, e in orgs.items()
        ],
        "fraccionamiento": episodios,
        "td_recurrente": recurrentes,
        "td_alto": altos,
        "proveedores": proveedores,
        "causales": Counter(o["causal"] for o in tds).most_common(),
    }


def meses_cerrados(hoy: date, n: int) -> list[str]:
    """Los n meses completos anteriores al actual."""
    y, m = hoy.year, hoy.month
    out = []
    for _ in range(n):
        y, m = (y - 1, 12) if m == 1 else (y, m - 1)
        out.append(bulk.month_key(y, m))
    return out[::-1]


def generar(out_dir: Path, raw_dir: Path, meses: int = 12) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    fuentes = {}
    ocs: list[dict] = []
    with httpx.Client(timeout=900) as http:
        for mes in meses_cerrados(date.today(), meses):
            version = bulk.remote_version(mes, http, base=OC_BASE)
            if version is None:
                log.warning("sin archivo de órdenes de compra para %s", mes)
                continue
            z = raw_dir / f"oc_{mes}.zip"
            if not z.exists():
                z = bulk.download(mes, raw_dir, http, base=OC_BASE, prefijo="oc")
            xs = leer_mes(z)
            log.info("%s: %d compras ágiles y tratos directos", mes, len(xs))
            ocs.extend(xs)
            fuentes[mes] = version
    resultado = {
        "generado": datetime.now(UTC).isoformat(timespec="minutes"),
        "fuentes": fuentes,
        "constantes": {
            "BANDA_TOPE": BANDA_TOPE,
            "FRACC_DIAS": FRACC_DIAS,
            "FRACC_MIN": FRACC_MIN,
            "TD_RECURRENTE": TD_RECURRENTE,
            "TD_ALTO_UTM": TD_ALTO_UTM,
            "UTM_CLP": UTM_CLP,
        },
        **analizar(ocs),
    }
    (out_dir / "compras.json").write_text(
        json.dumps(resultado, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    )
    return {
        "ordenes": len(ocs),
        "fraccionamiento": len(resultado["fraccionamiento"]),
        "td_recurrente": len(resultado["td_recurrente"]),
        "td_alto": len(resultado["td_alto"]),
    }
