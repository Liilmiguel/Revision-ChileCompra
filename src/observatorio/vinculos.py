"""Grupos de proveedores vinculados: empresas distintas (RUT distinto) que comparten dirección o
persona de contacto y compiten entre sí o se reparten compras.

Mercado Público no publica accionistas ni representantes en la descarga masiva; el detalle de
una orden de compra en la API sí trae la dirección del proveedor y el nombre de su contacto.
Consultar los ~80 mil proveedores tomaría días (~2,5 s por consulta), así que solo se consultan
candidatos por comportamiento en licitaciones (desde 2024):

- ofertaron exactamente el mismo total no redondo en alguna licitación (ver
  int_licitacion_senales_extra);
- casi siempre son los únicos dos oferentes (5+ licitaciones juntos, la mitad o más solos);
- son "acompañantes" (fct_par_proveedores).

Dos proveedores quedan vinculados si comparten dirección normalizada (calle, número y comuna)
o nombre de contacto. Un valor compartido por más de MAX_COMPARTIDO proveedores se descarta: es
una oficina compartida o un contador que inscribe a muchos clientes, no un vínculo.

Un vínculo no prueba que las empresas sean del mismo dueño ni una irregularidad. La pregunta
que abre es si compitieron de verdad cuando ofertaron en la misma licitación. La web muestra el
tipo de vínculo, no la dirección ni el nombre del contacto.
"""

from __future__ import annotations

import json
import logging
import re
from collections import defaultdict
from datetime import UTC, date, datetime
from pathlib import Path

from observatorio import bulk, compras
from observatorio.api_client import ApiError, MercadoPublicoClient
from observatorio.precios import normalizar

log = logging.getLogger(__name__)

MAX_COMPARTIDO = 6
SQL_PARES = """
with tot as (
    select o.codigo_externo, o.codigo_proveedor as p,
           sum(o.valor_total_ofertado) filter (where o.moneda_oferta = 'CLP') as total,
           bool_or(o.es_seleccionada) as gano
    from staging.stg_bulk__oferta o
    join marts.fct_licitacion l using (codigo_externo)
    where l.fecha_publicacion >= %(desde)s and o.codigo_proveedor is not null
    group by 1, 2
),
n as (select codigo_externo, count(*) as n from tot group by 1 having count(*) between 2 and 10)
select a.p, b.p, count(*) as juntos,
       count(*) filter (where n.n = 2) as solos,
       count(*) filter (where a.total = b.total and a.total >= 100000 and mod(a.total, 1000) <> 0) as identicas,
       count(*) filter (where a.gano) as gana_a,
       count(*) filter (where b.gano) as gana_b
from tot a
join tot b on a.codigo_externo = b.codigo_externo and a.p < b.p
join n on n.codigo_externo = a.codigo_externo
group by 1, 2
having count(*) >= 2
"""


def pares_licitaciones(conn, desde: str = "2024-01-01") -> dict[tuple[str, str], dict]:
    """Pares de proveedores que ofertaron juntos 2+ veces (licitaciones de 2 a 10 oferentes)."""
    out = {}
    for a, b, juntos, solos, identicas, gana_a, gana_b in conn.execute(SQL_PARES, {"desde": desde}):
        out[(a, b)] = {"juntos": juntos, "solos": solos, "identicas": identicas, "gana_a": gana_a, "gana_b": gana_b}
    return out


def candidatos(pares: dict, acompanantes: list[tuple[str, str]]) -> set[str]:
    out: set[str] = set()
    for (a, b), e in pares.items():
        if e["identicas"] >= 1 or (e["juntos"] >= 5 and e["solos"] >= 0.5 * e["juntos"]):
            out |= {a, b}
    for a, b in acompanantes:
        out |= {a, b}
    return out


def oc_por_proveedor(zips: list[Path], provs: set[str]) -> dict[str, str]:
    """Una orden de compra reciente de cada proveedor (para pedir su detalle a la API)."""
    out: dict[str, str] = {}
    for z in reversed(zips):  # primero los meses más recientes
        for r in bulk.read_rows(z):
            p = r.get("CodigoProveedor")
            if p in provs and p not in out and r.get("Codigo"):
                out[p] = r["Codigo"]
        if len(out) == len(provs):
            break
    return out


def consultar(client: MercadoPublicoClient, ocs: dict[str, str], cache: dict, guardar=lambda: None) -> int:
    """Completa `cache` con {proveedor: {direccion, comuna, contacto}}; guarda cada 100."""
    nuevos = 0
    for p, oc in ocs.items():
        if p in cache:
            continue
        try:
            d = client.orden_compra(oc)
        except ApiError as exc:
            log.warning("orden %s: %s", oc, client.mask(str(exc)))
            continue
        prov = (d or {}).get("Proveedor") or {}
        cache[p] = {
            "direccion": prov.get("Direccion"),
            "comuna": prov.get("Comuna"),
            "contacto": prov.get("NombreContacto"),
        }
        nuevos += 1
        if nuevos % 100 == 0:
            guardar()
            log.info("%d proveedores consultados", nuevos)
    guardar()
    return nuevos


def clave_direccion(direccion: str | None, comuna: str | None) -> str | None:
    """Calle + número + comuna, sin oficina ni depto (una torre de oficinas no vincula por sí
    sola: la oficina sí, pero suele venir escrita de mil formas)."""
    d = normalizar(direccion)
    d = re.split(r"\b(OF|OFICINA|DEPTO|DPTO|DEPARTAMENTO|LOCAL|PISO|BLOCK|CASA)\b", d)[0].strip()
    if not d or not re.search(r"\d", d) or len(d) < 6:
        return None
    return f"{d} | {normalizar(comuna)}"


def clave_contacto(nombre: str | None) -> str | None:
    n = normalizar(nombre)
    # Un contacto de una sola palabra o genérico ("VENTAS", "LICITACIONES") no identifica a nadie.
    if len(n.split()) < 2 or re.search(r"\b(VENTAS|LICITACIONES|CONTACTO|ADMINISTRACION|GERENCIA)\b", n):
        return None
    return n


def grupos(cache: dict) -> tuple[list[list[str]], list[tuple[str, str, str]], dict]:
    """Une proveedores por dirección o contacto compartido. Devuelve (grupos, aristas, descartes)."""
    por_valor: dict[tuple[str, str], set[str]] = defaultdict(set)
    for p, d in cache.items():
        if k := clave_direccion(d.get("direccion"), d.get("comuna")):
            por_valor[("direccion", k)].add(p)
        if k := clave_contacto(d.get("contacto")):
            por_valor[("contacto", k)].add(p)
    padre: dict[str, str] = {}

    def raiz(x: str) -> str:
        while padre.get(x, x) != x:
            padre[x] = padre.get(padre[x], padre[x])
            x = padre[x]
        return x

    aristas = []
    descartes = {"direccion": 0, "contacto": 0}
    for (tipo, _), ps in por_valor.items():
        if len(ps) < 2:
            continue
        if len(ps) > MAX_COMPARTIDO:
            descartes[tipo] += 1
            continue
        ps = sorted(ps)
        for q in ps[1:]:
            aristas.append((ps[0], q, tipo))
            padre[raiz(q)] = raiz(ps[0])
    miembros: dict[str, list[str]] = defaultdict(list)
    for p in {x for a, b, _ in aristas for x in (a, b)}:
        miembros[raiz(p)].append(p)
    return [sorted(v) for v in miembros.values()], aristas, descartes


def resumir(gs, aristas, pares, nombres: dict, montos: dict) -> list[dict]:
    """Un registro por grupo: miembros, tipos de vínculo y cuánto compitieron entre ellos."""
    tipos: dict[frozenset, set] = defaultdict(set)
    for a, b, t in aristas:
        tipos[frozenset((a, b))].add(t)
    out = []
    for g in gs:
        s = set(g)
        juntos = solos = identicas = 0
        for (a, b), e in pares.items():
            if a in s and b in s:
                juntos += e["juntos"]
                solos += e["solos"]
                identicas += e["identicas"]
        vinc = sorted({t for k, ts in tipos.items() if k <= s for t in ts})
        out.append(
            {
                "miembros": [[p, *(nombres.get(p) or [p, ""]), *(montos.get(p) or [0, 0])] for p in g],
                "vinculos": vinc,
                "juntos": juntos,
                "solos": solos,
                "identicas": identicas,
                "monto": sum(sum(montos.get(p) or [0, 0]) for p in g),
            }
        )
    return sorted(out, key=lambda x: (-x["juntos"], -x["monto"]))


def generar(conn, out_dir: Path, raw_dir: Path, ticket: str | None, max_consultas: int = 6000) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    cache_path = out_dir / "vinculos_cache.json"
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    pares = pares_licitaciones(conn)
    acomp = [tuple(r) for r in conn.execute("select ganador, acompanante from marts.fct_par_proveedores")]
    cand = candidatos(pares, acomp)
    log.info("%d pares, %d proveedores candidatos (%d ya consultados)", len(pares), len(cand), len(cand & set(cache)))
    zips = [raw_dir / f"oc_{m}.zip" for m in compras.meses_cerrados(date.today(), 12)]
    zips = [z for z in zips if z.exists()]
    faltan = cand - set(cache)
    if ticket and faltan:
        ocs = oc_por_proveedor(zips, faltan)
        ocs = dict(list(ocs.items())[:max_consultas])
        with MercadoPublicoClient(ticket) as client:
            consultar(client, ocs, cache, lambda: cache_path.write_text(json.dumps(cache, ensure_ascii=False)))
    gs, aristas, descartes = grupos({p: d for p, d in cache.items() if p in cand})
    nombres = {
        p: [n, r]
        for p, n, r in conn.execute("select codigo_proveedor, nombre_proveedor, rut_proveedor from marts.dim_proveedor")
    }
    montos: dict[str, list] = defaultdict(lambda: [0, 0])
    for p, m in conn.execute(
        "select codigo_proveedor, sum(monto_adjudicado) from marts.fct_adjudicacion a "
        "join marts.fct_licitacion l using (codigo_externo) "
        "where a.moneda = 'CLP' and l.fecha_publicacion >= '2024-01-01' group by 1"
    ):
        montos[p][0] = round(float(m or 0))
    oc_path = out_dir / "proveedores_oc.json"
    if oc_path.exists():
        d = json.loads(oc_path.read_text())
        ix = {c: i for i, c in enumerate(d["campos"])}
        for f in d["filas"]:
            montos[f[ix["prov"]]][1] = f[ix["ag_monto"]] + f[ix["td_monto"]]
    resultado = {
        "generado": datetime.now(UTC).isoformat(timespec="minutes"),
        "constantes": {"MAX_COMPARTIDO": MAX_COMPARTIDO},
        "resumen": {
            "pares": len(pares),
            "candidatos": len(cand),
            "consultados": len(cand & set(cache)),
            "grupos": len(gs),
            "descartes": descartes,
        },
        "campos_miembro": ["prov", "nombre", "rut", "monto_licitaciones", "monto_compras_directas"],
        "grupos": resumir(gs, aristas, pares, nombres, montos),
    }
    (out_dir / "vinculos.json").write_text(json.dumps(resultado, ensure_ascii=False, separators=(",", ":")))
    return resultado["resumen"]
