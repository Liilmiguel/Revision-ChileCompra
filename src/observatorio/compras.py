"""Compras Ágiles y tratos directos: órdenes de compra sin licitación pública.

Fuente: descarga masiva de órdenes de compra (oc-da), un zip mensual de ~100 MB con una
fila por ítem. No usa la base de datos: agrega por orden de compra y escribe
data/compras/compras.json para la versión web.

- Compra Ágil: compras de hasta 100 UTM con impuestos, por cotización simple. El tope se
  mide en los datos: en septiembre de 2026 no hay ninguna sobre ~$7,2 millones (100 UTM
  de ~$72.000) y la cantidad crece de forma marcada entre 90 y 100 UTM.
- Trato directo: contratación sin concurso, con una causal legal (proveedor único,
  emergencia, etc.).

Señales (pistas para revisar, no pruebas). Se calibraron revisando casos para que cada una
exija más de una coincidencia; ver docs/fase3_preguntas.md.
- compra dividida: 2+ Compras Ágiles de la misma unidad de compra al mismo proveedor, con la
  misma especificación de un bien, en 7 días, que juntas superan el tope. Agrupar por
  organismo (un servicio de salud con varios hospitales) o por rubro marcaba compras
  distintas; la especificación exacta descarta los consumos por cirugía o por paciente.
- compras repetidas sobre el tope: 3+ Compras Ágiles de la misma unidad, proveedor y
  código de producto en 30 días que juntas superan el tope (sin las ya contadas como compra
  dividida). Es una necesidad continua que debió ir a licitación o convenio; confianza media.
- bajo el tope: Compra Ágil entre 90 % y 100 % del tope del mes. Una por sí sola no dice
  nada; un organismo con mucho más que la proporción nacional sí (la web exige 100+ compras
  y una diferencia estadísticamente clara).
- emergencia repetida: 3+ tratos directos por emergencia del mismo organismo al mismo
  proveedor por el mismo bien a lo largo de 180+ días. En servicios (turnos, traslados de
  pacientes) cada caso puede ser urgente, así que se miran solo bienes.
- tratos directos encadenados: tratos directos de causales de monto menor (bajo 100 o 30
  UTM) de la misma unidad, proveedor y bien que en 30 días suman más de 100 UTM (los
  exámenes o traslados por paciente se repiten legítimamente: solo bienes).

Las señales de bienes descartan también servicios codificados como bienes, por el texto de la
especificación (SERVICIO_TEXTO).
- trato directo de monto alto: sobre 1.000 UTM; es contexto, con las señales anteriores que
  lo acompañan.
"""

from __future__ import annotations

import json
import logging
import re
from collections import Counter, defaultdict
from datetime import UTC, date, datetime
from pathlib import Path

import httpx

from observatorio import bulk
from observatorio.precios import GENERICAS, es_servicio, normalizar

log = logging.getLogger(__name__)

OC_BASE = "https://transparenciachc.blob.core.windows.net/oc-da/"
UTM_CLP = 72000  # aproximado 2025–2026; solo para el umbral de 1.000 UTM de tratos directos
BANDA_TOPE = 0.9
DIVISION_DIAS = 7
REPETIDAS_DIAS = 30
REPETIDAS_MIN = 3
EMERGENCIA_MIN = 3
EMERGENCIA_DIAS = 180
ENCADENADO_DIAS = 30
ENCADENADO_UTM = 100 * 1.19  # 100 UTM más IVA, como el tope de la Compra Ágil
# Servicios codificados como bienes (el código ONU de un equipo en su mantención, un examen
# por paciente): se reconocen por la especificación y quedan fuera de las señales de bienes.
SERVICIO_TEXTO = re.compile(
    r"\b(SERVICIOS?|ARRIENDO|MANTENCION|MANTENIMIENTO|REPARACION|INSTALACION|TRASLADOS?|TRANSPORTE|"
    r"ASISTENCIA|PRESTACION(ES)?|EXAMEN(ES)?|ESTADIA|ACONDICIONAMIENTO|ATENCION|CONSULTA|ASESORIA|SOPORTE|"
    r"PROCEDIMIENTO|CIRUGIA|HOSPITALIZACION|CAPACITACION|PROCESAMIENTO|ANALISIS|ESTUDIO|EVALUACION)\b"
)
CAUSALES_MENORES = ("inferior a 100 UTM", "inferiores a 30 UTM", "inferiores a 10 UTM")
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

    El archivo trae una fila por ítem: la cabecera sale de la primera fila; el rubro y la
    especificación, del ítem de mayor monto. Se omiten las órdenes canceladas o eliminadas."""
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
                "unidad": r.get("CodigoUnidadCompra") or r.get("CodigoOrganismoPublico"),
                "unidad_nombre": (r.get("UnidadCompra") or "")[:60],
                "region": (r.get("RegionUnidadCompra") or "").strip() or None,
                "prov": r.get("CodigoProveedor"),
                "prov_nombre": r.get("NombreProveedor"),
                "prov_rut": r.get("RutSucursal"),
                "monto": _num(r.get("MontoTotalOC_PesosChilenos")),
                "rubro": None,
                "rubro2": None,
                "nombre": (r.get("Nombre") or "")[:140],
                "onu": set(),
                "bien": False,
                "espec": "",
            }
        if not oc:
            continue
        onu = r.get("codigoProductoONU")
        if onu and len(oc["onu"]) < 20:
            oc["onu"].add(onu)
        oc["bien"] = oc["bien"] or (bool(onu) and not es_servicio(onu))
        neto = _num(r.get("totalLineaNeto"))
        if oc["rubro"] is None or neto > linea_max[c]:
            oc["rubro"], oc["rubro2"] = r.get("RubroN1"), r.get("RubroN2")
            oc["espec"] = normalizar(r.get("EspecificacionComprador"))[:90]
            oc["onu_principal"] = onu
            linea_max[c] = neto
    return [o for o in ocs.values() if o and o["fecha"] and o["org"] and o["prov"]]


def tope_mes(ags: list[dict]) -> float | None:
    """Tope de Compra Ágil del mes medido en los datos: percentil 99,95 de los montos
    (robusto a una orden mal digitada; el tope real queda a menos de 1 % de este valor)."""
    montos = sorted(o["monto"] for o in ags if o["monto"] > 0)
    if len(montos) < 1000:
        return None
    return montos[int(0.9995 * (len(montos) - 1))]


def es_bien(o: dict) -> bool:
    """La orden compra un bien: algún ítem con código de producto que no es de servicio y una
    especificación que no describe un servicio."""
    return o["bien"] and not SERVICIO_TEXTO.search(o["espec"] or "")


def _dia(o: dict) -> int:
    return date.fromisoformat(o["fecha"]).toordinal()


def _ventanas(xs: list[dict], dias: int, minimo: int, supera) -> list[list[dict]]:
    """Grupos maximales de órdenes (ordenadas por fecha) donde alguna ventana de `dias` días
    tiene `minimo`+ órdenes que cumplen `supera(ventana)`; ventanas marcadas a menos de
    `dias` días se unen en un mismo episodio."""
    xs = sorted(xs, key=lambda o: (o["fecha"], o["codigo"]))
    d = [_dia(o) for o in xs]
    marcadas = [False] * len(xs)
    j = 0
    for i in range(len(xs)):
        while d[i] - d[j] > dias:
            j += 1
        if i - j + 1 >= minimo and supera(xs[j : i + 1]):
            for k in range(j, i + 1):
                marcadas[k] = True
    episodios, actual = [], []
    for o, di, m in zip(xs, d, marcadas, strict=True):
        if not m:
            continue
        if actual and di - _dia(actual[-1]) > dias:
            episodios.append(actual)
            actual = []
        actual.append(o)
    if actual:
        episodios.append(actual)
    return episodios


def _sobre_tope(w: list[dict], topes: dict[str, float]) -> bool:
    """Las órdenes de la ventana suman más que el tope de Compra Ágil del mes de la última."""
    t = topes.get(w[-1]["fecha"][:7])
    return t is not None and sum(o["monto"] for o in w) > t


def _episodio(ep: list[dict], producto: str, **extra) -> dict:
    o0 = ep[0]
    return {
        "org": o0["org"],
        "unidad": o0["unidad_nombre"],
        "prov": o0["prov"],
        "producto": producto,
        "desde": ep[0]["fecha"],
        "hasta": ep[-1]["fecha"],
        "n": len(ep),
        "monto": round(sum(o["monto"] for o in ep)),
        "codigos": [o["codigo"] for o in ep][:50],
        **extra,
    }


def compra_dividida(ags: list[dict], topes: dict[str, float]) -> list[dict]:
    """2+ Compras Ágiles de la misma unidad, proveedor y especificación exacta de un bien en
    DIVISION_DIAS días que juntas superan el tope del mes."""
    grupos: dict[tuple, list[dict]] = defaultdict(list)
    for o in ags:
        if es_bien(o) and len(o["espec"]) >= 8 and not GENERICAS.search(o["espec"]):
            grupos[(o["unidad"], o["prov"], o["espec"])].append(o)
    out = []
    for (_, _, espec), xs in grupos.items():
        if len(xs) < 2:
            continue
        for ep in _ventanas(xs, DIVISION_DIAS, 2, lambda w: _sobre_tope(w, topes)):
            montos = [o["monto"] for o in ep]
            t = topes.get(ep[0]["fecha"][:7]) or max(topes.values())
            out.append(
                _episodio(ep, espec, veces_tope=round(sum(montos) / t, 2), iguales=max(montos) <= 1.02 * min(montos))
            )
    return sorted(out, key=lambda e: -e["monto"])


def compras_repetidas(ags: list[dict], topes: dict[str, float], excluir: set[str]) -> list[dict]:
    """3+ Compras Ágiles de la misma unidad, proveedor y código de producto en REPETIDAS_DIAS
    días que juntas superan el tope (sin las órdenes ya contadas como compra dividida)."""
    grupos: dict[tuple, list[dict]] = defaultdict(list)
    for o in ags:
        if o["codigo"] not in excluir and o.get("onu_principal"):
            grupos[(o["unidad"], o["prov"], o["onu_principal"])].append(o)
    out = []
    for xs in grupos.values():
        if len(xs) < REPETIDAS_MIN:
            continue
        for ep in _ventanas(xs, REPETIDAS_DIAS, REPETIDAS_MIN, lambda w: _sobre_tope(w, topes)):
            t = topes.get(ep[0]["fecha"][:7]) or max(topes.values())
            out.append(
                _episodio(
                    ep, ep[0]["espec"] or ep[0]["rubro2"] or "", veces_tope=round(sum(o["monto"] for o in ep) / t, 2)
                )
            )
    return sorted(out, key=lambda e: -e["monto"])


def emergencia_repetida(tds: list[dict]) -> list[dict]:
    """3+ tratos directos por emergencia del mismo organismo al mismo proveedor por el mismo
    bien (código de producto) repartidos en EMERGENCIA_DIAS+ días."""
    grupos: dict[tuple, list[dict]] = defaultdict(list)
    for o in tds:
        if (
            "mergencia" in (o["causal"] or "")
            and es_bien(o)
            and o.get("onu_principal")
            and not es_servicio(o["onu_principal"])
        ):
            grupos[(o["org"], o["prov"], o["onu_principal"])].append(o)
    out = []
    for xs in grupos.values():
        xs.sort(key=lambda o: o["fecha"])
        if len(xs) >= EMERGENCIA_MIN and _dia(xs[-1]) - _dia(xs[0]) >= EMERGENCIA_DIAS:
            out.append(_episodio(xs, xs[0]["espec"] or xs[0]["rubro2"] or ""))
    return sorted(out, key=lambda e: -e["monto"])


def td_encadenados(tds: list[dict]) -> list[dict]:
    """Tratos directos de causales de monto menor (bajo 100 o 30 UTM) de la misma unidad,
    proveedor y producto que en ENCADENADO_DIAS días suman más de 100 UTM con IVA."""
    grupos: dict[tuple, list[dict]] = defaultdict(list)
    for o in tds:
        if any(c in (o["causal"] or "") for c in CAUSALES_MENORES) and es_bien(o) and o.get("onu_principal"):
            grupos[(o["unidad"], o["prov"], o["onu_principal"])].append(o)
    limite = ENCADENADO_UTM * UTM_CLP
    out = []
    for xs in grupos.values():
        if len(xs) < 2:
            continue
        for ep in _ventanas(xs, ENCADENADO_DIAS, 2, lambda w: sum(o["monto"] for o in w) > limite):
            out.append(
                _episodio(
                    ep,
                    ep[0]["espec"] or ep[0]["rubro2"] or "",
                    causal=Counter(o["causal"] for o in ep).most_common(1)[0][0],
                )
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

    division = compra_dividida(ags, topes)
    en_division = {c for e in division for c in e["codigos"]}
    repetidas = compras_repetidas(ags, topes, en_division)
    emergencias = emergencia_repetida(tds)
    encadenados = td_encadenados(tds)

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
                "division_n": 0,
            },
        )
        if o["tipo"] == "AG":
            e["ag_n"] += 1
            e["ag_monto"] += o["monto"]
            e["ag_banda"] += bool(o.get("banda"))
            e["division_n"] += o["codigo"] in en_division
        else:
            e["td_n"] += 1
            e["td_monto"] += o["monto"]

    # Tratos directos de monto alto, con las señales de tratos directos que los acompañan.
    marca = {c: "emergencia repetida" for e in emergencias for c in e["codigos"]}
    marca.update({c: "encadenado" for e in encadenados for c in e["codigos"]})
    altos = sorted(
        (
            {
                **{k: o[k] for k in ("codigo", "fecha", "org", "prov", "monto", "causal", "nombre", "rubro")},
                "senal": marca.get(o["codigo"]),
            }
            for o in tds
            if o["monto"] > TD_ALTO_UTM * UTM_CLP
        ),
        key=lambda o: -o["monto"],
    )

    listas = {
        "division": division,
        "repetidas": repetidas,
        "emergencia_repetida": emergencias,
        "td_encadenados": encadenados,
        "td_alto": altos,
    }
    listas = {k: v[:MAX_LISTA] for k, v in listas.items()}
    usados = {e["prov"] for lista in listas.values() for e in lista}
    proveedores = {}
    for o in ocs:
        if o["prov"] in usados and o["prov"] not in proveedores:
            proveedores[o["prov"]] = [o["prov_nombre"], o.get("prov_rut")]

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
                e["division_n"],
            ]
            for c, e in orgs.items()
        ],
        **listas,
        "proveedores": proveedores,
        "causales": Counter(o["causal"] for o in tds).most_common(),
        "por_proveedor": por_proveedor(ocs, en_division),
    }


# Campos de cada fila de proveedores_oc.json.
CAMPOS_PROVEEDOR = [
    "prov", "nombre", "rut", "ag_n", "ag_monto", "ag_banda", "ag_fracc", "td_n", "td_monto", "td_emergencia", "orgs",
]  # fmt: skip


def por_proveedor(ocs: list[dict], en_division: set[str]) -> list[list]:
    """Compras Ágiles y tratos directos de cada proveedor (pestaña Proveedores de la web)."""
    P: dict[str, dict] = {}
    for o in ocs:
        e = P.get(o["prov"])
        if e is None:
            e = P[o["prov"]] = {
                "nombre": (o["prov_nombre"] or "")[:80],
                "rut": o.get("prov_rut"),
                "ag_n": 0,
                "ag_monto": 0.0,
                "ag_banda": 0,
                "ag_fracc": 0,
                "td_n": 0,
                "td_monto": 0.0,
                "td_emergencia": 0,
                "orgs": set(),
            }
        e["orgs"].add(o["org"])
        if o["tipo"] == "AG":
            e["ag_n"] += 1
            e["ag_monto"] += o["monto"]
            e["ag_banda"] += bool(o.get("banda"))
            e["ag_fracc"] += o["codigo"] in en_division
        else:
            e["td_n"] += 1
            e["td_monto"] += o["monto"]
            e["td_emergencia"] += "mergencia" in (o["causal"] or "")
    return [
        [c, e["nombre"], e["rut"], e["ag_n"], round(e["ag_monto"]), e["ag_banda"], e["ag_fracc"], e["td_n"],
         round(e["td_monto"]), e["td_emergencia"], len(e["orgs"])]
        for c, e in P.items()
    ]  # fmt: skip


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
            "DIVISION_DIAS": DIVISION_DIAS,
            "REPETIDAS_DIAS": REPETIDAS_DIAS,
            "REPETIDAS_MIN": REPETIDAS_MIN,
            "EMERGENCIA_MIN": EMERGENCIA_MIN,
            "EMERGENCIA_DIAS": EMERGENCIA_DIAS,
            "ENCADENADO_DIAS": ENCADENADO_DIAS,
            "ENCADENADO_UTM": ENCADENADO_UTM,
            "TD_ALTO_UTM": TD_ALTO_UTM,
            "UTM_CLP": UTM_CLP,
        },
        **analizar(ocs),
    }
    # Por proveedor va aparte (~6 MB): solo lo carga la pestaña Proveedores.
    por_prov = resultado.pop("por_proveedor")
    (out_dir / "proveedores_oc.json").write_text(
        json.dumps({"campos": CAMPOS_PROVEEDOR, "filas": por_prov}, ensure_ascii=False, separators=(",", ":"))
    )
    (out_dir / "compras.json").write_text(
        json.dumps(resultado, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    )
    return {
        "ordenes": len(ocs),
        "division": len(resultado["division"]),
        "repetidas": len(resultado["repetidas"]),
        "emergencia_repetida": len(resultado["emergencia_repetida"]),
        "td_encadenados": len(resultado["td_encadenados"]),
        "td_alto": len(resultado["td_alto"]),
    }
