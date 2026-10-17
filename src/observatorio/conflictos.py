"""Posibles conflictos de interés: autoridades y funcionarios que declaran participación en una
sociedad que le vende al organismo donde trabajan.

Fuentes:
- Participaciones en sociedades de las declaraciones de intereses y patrimonio (InfoProbidad,
  Ley 20.880), ya extraídas a un JSON con filas {rut_sociedad, nombre_sociedad, tipo,
  porcentaje, titular, declarante_nombre, cargo, servicio, fecha_declaracion, url_declaracion}.
- Proveedores del Estado por RUT: licitaciones adjudicadas (marts) y órdenes de compra de todos
  los tipos de los últimos 12 meses (descarga masiva oc-da).

El organismo del declarante viene como texto libre ("I. Municipalidad de Puente Alto") y se
empareja con los nombres de organismos compradores por palabras en común. Cada fila trae la
calidad del emparejamiento; las dudosas se muestran aparte para revisión manual.

Las acciones de sociedades abiertas (LATAM, Copec, Entel…) aparecen en decenas de
declaraciones y no dan injerencia: una sociedad declarada por MAX_DECLARANTES o más personas
se marca `abierta` y la web la oculta por defecto.

Una coincidencia no es un conflicto probado: el funcionario puede haberse abstenido o no tener
injerencia en la compra. Es la pregunta a hacer.
"""

from __future__ import annotations

import json
import logging
import re
from collections import defaultdict
from datetime import UTC, date, datetime
from pathlib import Path

from observatorio import bulk, compras
from observatorio.precios import normalizar

log = logging.getLogger(__name__)

# Palabras que no distinguen organismos entre sí. «Servicio», «Gobierno», «Subsecretaría» sí
# distinguen (Gobierno Regional de O'Higgins no es la Universidad de O'Higgins).
VACIAS = {"I", "IL", "ILUSTRE", "DE", "DEL", "LA", "LAS", "LOS", "EL", "Y", "EN", "PARA", "POR", "A", "AL", "CHILE"}
ABREVIATURAS = {"CORP": "CORPORACION", "MUNIC": "MUNICIPALIDAD", "MINIST": "MINISTERIO", "SERV": "SERVICIO"}
MIN_SIMILITUD = 0.6
MAX_DECLARANTES = 3


def normalizar_rut(rut: str | None) -> str | None:
    if not rut:
        return None
    r = re.sub(r"[^0-9Kk]", "", rut).upper()
    if len(r) < 2:
        return None
    return f"{int(r[:-1])}-{r[-1]}" if r[:-1].isdigit() else None


def palabras(nombre: str | None) -> set[str]:
    ws = (ABREVIATURAS.get(w, w) for w in normalizar(nombre).split())
    return {w for w in ws if w not in VACIAS and len(w) > 1}


def similitud(a: str | None, b: str | None) -> float:
    """Palabras en común sobre las del nombre más largo: "I. Municipalidad de X" calza con
    "Municipalidad de X", pero "Poder Judicial" no con "Corporación Administrativa del Poder
    Judicial" (quien declara en un organismo grande rara vez decide las compras de otro)."""
    pa, pb = palabras(a), palabras(b)
    if not pa or not pb:
        return 0.0
    return len(pa & pb) / max(len(pa), len(pb))


def emparejar_organismo(servicio: str | None, organismos: dict[str, str]) -> tuple[str | None, float]:
    """Organismo comprador más parecido al servicio declarado: (código, similitud)."""
    mejor, puntaje = None, 0.0
    ps = palabras(servicio)
    if not ps:
        return None, 0.0
    for codigo, nombre in organismos.items():
        s = similitud(servicio, nombre)
        # Desempate: el nombre de organismo con menos palabras sobrantes.
        if s > puntaje or (s == puntaje and mejor and len(palabras(nombre)) < len(palabras(organismos[mejor]))):
            mejor, puntaje = codigo, s
    return mejor, round(puntaje, 2)


def compras_por_organismo(zips: list[Path]) -> tuple[dict, dict, dict]:
    """Órdenes de compra (todos los tipos) por (organismo, RUT del proveedor):
    {(org, rut): [n, monto, {tipos}]}, nombres de organismos y {rut: nombre del proveedor}."""
    agg: dict[tuple, list] = defaultdict(lambda: [0, 0.0, set()])
    orgs: dict[str, str] = {}
    provs: dict[str, str] = {}
    vistas: set[str] = set()
    for z in zips:
        for r in bulk.read_rows(z):
            c = r.get("Codigo")
            if not c or c in vistas:
                continue
            vistas.add(c)
            estado = r.get("Estado") or ""
            if "ancel" in estado or "limin" in estado:
                continue
            rut = normalizar_rut(r.get("RutSucursal"))
            org = r.get("CodigoOrganismoPublico")
            if not rut or not org:
                continue
            tipo = "AG" if r.get("EsCompraAgil") == "Si" else "TD" if r.get("EsTratoDirecto") == "Si" else r.get("Tipo")
            e = agg[(org, rut)]
            e[0] += 1
            try:
                e[1] += float((r.get("MontoTotalOC_PesosChilenos") or "0").replace(",", "."))
            except ValueError:
                pass
            e[2].add(tipo)
            orgs.setdefault(org, r.get("OrganismoPublico") or org)
            provs.setdefault(rut, r.get("NombreProveedor") or "")
        log.info("%s: %d pares organismo-proveedor", z.name, len(agg))
    return agg, orgs, provs


def cruzar(participaciones: list[dict], oc: dict, lic: dict, orgs: dict[str, str], proveedores: dict) -> dict:
    """Une participaciones con compras. Devuelve conflictos (el organismo del declarante le compra
    a la sociedad) y participaciones en proveedores del Estado (cualquier organismo)."""
    por_rut_oc: dict[str, list] = defaultdict(list)
    for (org, rut), v in oc.items():
        por_rut_oc[rut].append((org, v))
    por_rut_lic: dict[str, list] = defaultdict(list)
    for (org, rut), v in lic.items():
        por_rut_lic[rut].append((org, v))
    cache_org: dict[str, tuple] = {}
    declarantes: dict[str, set] = defaultdict(set)
    for f in participaciones:
        if rut := normalizar_rut(f.get("rut_sociedad")):
            declarantes[rut].add(f.get("declarante_nombre"))
    conflictos, en_proveedores = [], []
    for f in participaciones:
        rut = normalizar_rut(f.get("rut_sociedad"))
        if not rut or (rut not in por_rut_oc and rut not in por_rut_lic):
            continue
        total_oc = sum(v[1] for _, v in por_rut_oc.get(rut, []))
        total_lic = sum(v[1] for _, v in por_rut_lic.get(rut, []))
        base = {
            "declarante": f.get("declarante_nombre"),
            "cargo": f.get("cargo"),
            "servicio": f.get("servicio"),
            "titular": f.get("titular"),
            "rut_sociedad": rut,
            "sociedad": f.get("nombre_sociedad") or proveedores.get(rut, ""),
            "tipo": f.get("tipo"),
            "porcentaje": f.get("porcentaje"),
            "fecha_declaracion": f.get("fecha_declaracion"),
            "url": f.get("url_declaracion"),
            "abierta": len(declarantes[rut]) >= MAX_DECLARANTES,
        }
        en_proveedores.append({**base, "monto_oc": round(total_oc), "monto_lic": round(total_lic)})
        servicio = f.get("servicio") or ""
        if servicio not in cache_org:
            cache_org[servicio] = emparejar_organismo(servicio, orgs)
        org, sim = cache_org[servicio]
        if not org or sim < MIN_SIMILITUD:
            continue
        v_oc = dict(por_rut_oc.get(rut, [])).get(org)
        v_lic = dict(por_rut_lic.get(rut, [])).get(org)
        if not v_oc and not v_lic:
            continue
        conflictos.append(
            {
                **base,
                "org": org,
                "org_nombre": orgs.get(org, org),
                "similitud": sim,
                "oc_n": v_oc[0] if v_oc else 0,
                "oc_monto": round(v_oc[1]) if v_oc else 0,
                "oc_tipos": sorted(v_oc[2]) if v_oc else [],
                "lic_n": v_lic[0] if v_lic else 0,
                "lic_monto": round(v_lic[1]) if v_lic else 0,
            }
        )
    conflictos.sort(key=lambda x: -(x["oc_monto"] + x["lic_monto"]))
    en_proveedores.sort(key=lambda x: -(x["monto_oc"] + x["monto_lic"]))
    return {"conflictos": conflictos, "participaciones_en_proveedores": en_proveedores}


def generar(conn, participaciones_path: Path, out_dir: Path, raw_dir: Path) -> dict:
    datos = json.loads(participaciones_path.read_text())
    filas = datos["filas"] if isinstance(datos, dict) else datos
    zips = [raw_dir / f"oc_{m}.zip" for m in compras.meses_cerrados(date.today(), 12)]
    oc, orgs, provs = compras_por_organismo([z for z in zips if z.exists()])
    # Licitaciones adjudicadas desde 2024 por (organismo, RUT del proveedor), en pesos.
    lic: dict[tuple, list] = {}
    for org, org_nombre, rut, n, monto in conn.execute(
        """
        select l.codigo_organismo, max(l.nombre_organismo), p.rut_proveedor, count(distinct a.codigo_externo),
               sum(a.monto_adjudicado)
        from marts.fct_adjudicacion a
        join marts.fct_licitacion l using (codigo_externo)
        join marts.dim_proveedor p using (codigo_proveedor)
        where a.moneda = 'CLP' and l.fecha_publicacion >= '2024-01-01'
        group by 1, 3
        """
    ):
        r = normalizar_rut(rut)
        if r:
            lic[(org, r)] = [n, float(monto or 0)]
            orgs.setdefault(org, org_nombre)
    resultado = {
        "generado": datetime.now(UTC).isoformat(timespec="minutes"),
        "fuente": datos.get("fuente") if isinstance(datos, dict) else None,
        "participaciones": len(filas),
        "cobertura": datos.get("cobertura") if isinstance(datos, dict) else None,
        "constantes": {"MIN_SIMILITUD": MIN_SIMILITUD, "MAX_DECLARANTES": MAX_DECLARANTES},
        **cruzar(filas, oc, lic, orgs, provs),
    }
    (out_dir / "conflictos.json").write_text(json.dumps(resultado, ensure_ascii=False, separators=(",", ":")))
    return {
        "participaciones": len(filas),
        "en_proveedores": len(resultado["participaciones_en_proveedores"]),
        "conflictos": len(resultado["conflictos"]),
    }
