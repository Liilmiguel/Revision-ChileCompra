"""Métricas de las 4 preguntas del observatorio, sobre el snapshot Parquet con DuckDB.

Una sola definición para el análisis escrito (analysis/) y el dashboard, así ambos
dan los mismos números. Definiciones en docs/fase3_preguntas.md.

1. Competencia: ¿cuántas empresas compiten por cada licitación y cuántas tienen un solo oferente?
2. Precio: ¿se adjudica por sobre o por debajo del monto estimado, y cambia con la competencia?
3. Concentración: ¿cuán concentradas están las compras de cada organismo en pocos proveedores?
4. Proceso: ¿cuántas licitaciones fracasan (desiertas, revocadas) y cuánto demoran?
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import duckdb
import pandas as pd

# Licitaciones con al menos esta cantidad de días desde el cierre se consideran
# "maduras": ya tuvieron tiempo de adjudicarse, declararse desiertas o revocarse.
DIAS_MADUREZ = 120
# Umbral de "adjudicado sobre lo estimado" para la señal de alerta.
RAZON_SOBRE_ESTIMADO = 1.2
# Señales de riesgo: (columna, etiqueta, peso). Los pesos los fija dbt (var senales); aquí solo se
# documentan para mostrarlos.
SENALES = [
    ("s_oferente_unico", "Oferente único", 25),
    ("s_competencia_descalificada", "Competencia descalificada", 25),
    ("s_sobre_oferta_barata", "Pagó 50 % más que la oferta más barata", 20),
    ("s_sobre_estimado", "Adjudicado más de 20 % sobre lo estimado", 15),
    ("s_plazo_corto", "Plazo de ofertas muy corto", 10),
    ("s_precio_referencia", "Precio unitario más de 5 veces la referencia", 5),
]
RIESGO_ALTO = 40  # al menos dos señales, una de ellas fuerte
RIESGO_MEDIO = 20
# Mínimo de licitaciones adjudicadas para comparar organismos o grupos entre sí.
MIN_GRUPO = 30
# Bajo esta razón adjudicado/estimado la licitación casi siempre es un convenio de
# suministro adjudicado por precio unitario (p. ej. fotocopias a $15 con un estimado de
# $28 millones): la razón no mide precio y se excluye de la pregunta 2.
RAZON_PRECIO_UNITARIO = 0.1


@dataclass
class Filtros:
    desde: date | None = None
    hasta: date | None = None
    tipos: list[str] = field(default_factory=list)
    regiones: list[str] = field(default_factory=list)
    sectores: list[str] = field(default_factory=list)
    organismos: list[str] = field(default_factory=list)

    def where(self) -> tuple[str, list]:
        conds, params = ["true"], []
        if self.desde:
            conds.append("fecha_publicacion >= ?")
            params.append(self.desde)
        if self.hasta:
            conds.append("fecha_publicacion <= ?")
            params.append(self.hasta)
        for col, values in (
            ("tipo", self.tipos),
            ("region_unidad", self.regiones),
            ("sector", self.sectores),
            ("codigo_organismo", self.organismos),
        ):
            if values:
                conds.append(f"{col} in ({', '.join('?' for _ in values)})")
                params.extend(values)
        return " and ".join(conds), params


class Observatorio:
    def __init__(self, snapshot_dir: Path) -> None:
        self.dir = snapshot_dir
        self.meta = json.loads((snapshot_dir / "meta.json").read_text())
        self.db = duckdb.connect()
        for name in ("licitaciones", "adjudicaciones", "proveedores", "pares"):
            path = str(snapshot_dir / f"{name}.parquet").replace("'", "''")
            self.db.execute(f"create view {name} as select * from read_parquet('{path}')")
        self.corte: date = self.db.execute("select max(fecha_publicacion) from licitaciones").fetchone()[0]

    def q(self, sql: str, params: list | None = None) -> pd.DataFrame:
        return self.db.execute(sql, params or []).df()

    def _lic(self, f: Filtros) -> tuple[str, list]:
        """CTE `l` con las licitaciones filtradas."""
        where, params = f.where()
        return f"with l as (select * from licitaciones where {where})", params

    # ---------- catálogos para los filtros ----------

    def opciones(self) -> dict[str, pd.DataFrame]:
        return {
            "tipos": self.q(
                "select tipo, any_value(tipo_descripcion) d, min(tipo_orden) o, count(*) n "
                "from licitaciones group by tipo order by o, n desc"
            ),
            "regiones": self.q(
                "select region_unidad r, count(*) n from licitaciones where region_unidad is not null "
                "group by 1 order by 1"
            ),
            "sectores": self.q(
                "select sector s, count(*) n from licitaciones where sector is not null group by 1 order by n desc"
            ),
            "organismos": self.q(
                "select codigo_organismo c, any_value(nombre_organismo) nombre, count(*) n "
                "from licitaciones group by 1 order by n desc"
            ),
            "meses": self.q("select min(mes_publicacion) desde, max(mes_publicacion) hasta from licitaciones"),
        }

    # ---------- resumen ----------

    def resumen(self, f: Filtros) -> dict:
        cte, p = self._lic(f)
        r = self.q(
            f"""{cte}
            select count(*) n,
                   count(*) filter (where estado_grupo = 'Adjudicada') adjudicadas,
                   sum(monto_adjudicado) filter (where moneda_adjudicada = 'CLP') monto_clp,
                   count(distinct codigo_organismo) organismos
            from l""",
            p,
        ).iloc[0]
        prov = self.q(
            f"""{cte}
            select count(distinct a.codigo_proveedor) n from adjudicaciones a join l using (codigo_externo)""",
            p,
        ).iloc[0]["n"]
        return {**r.to_dict(), "proveedores": int(prov)}

    def mensual(self, f: Filtros) -> pd.DataFrame:
        cte, p = self._lic(f)
        return self.q(
            f"""{cte}
            select mes_publicacion mes, count(*) publicadas,
                   count(*) filter (where estado_grupo = 'Adjudicada') adjudicadas,
                   sum(monto_adjudicado) filter (where moneda_adjudicada = 'CLP') monto_clp
            from l group by 1 order by 1""",
            p,
        )

    # ---------- 1. competencia ----------

    _ADJ_CON_OFERTAS = "estado_grupo = 'Adjudicada' and n_proveedores_oferentes > 0"

    def competencia_kpis(self, f: Filtros) -> dict:
        cte, p = self._lic(f)
        return (
            self.q(
                f"""{cte}
                select count(*) n,
                       avg(es_oferente_unico::int) pct_unico,
                       median(n_proveedores_oferentes) mediana_oferentes,
                       avg(n_proveedores_oferentes) media_oferentes
                from l where {self._ADJ_CON_OFERTAS}""",
                p,
            )
            .iloc[0]
            .to_dict()
        )

    def distribucion_oferentes(self, f: Filtros) -> pd.DataFrame:
        cte, p = self._lic(f)
        return self.q(
            f"""{cte}
            select case when n_proveedores_oferentes >= 10 then '10+'
                        else n_proveedores_oferentes::varchar end as oferentes,
                   least(n_proveedores_oferentes, 10) orden, count(*) n
            from l where {self._ADJ_CON_OFERTAS}
            group by 1, 2 order by 2""",
            p,
        )

    def competencia_mensual(self, f: Filtros) -> pd.DataFrame:
        cte, p = self._lic(f)
        return self.q(
            f"""{cte}
            select mes_publicacion mes, count(*) n, avg(es_oferente_unico::int) pct_unico
            from l where {self._ADJ_CON_OFERTAS} group by 1 order by 1""",
            p,
        )

    def competencia_por(self, f: Filtros, dim: str, min_n: int = MIN_GRUPO) -> pd.DataFrame:
        assert dim in {"tipo_descripcion", "region_unidad", "sector", "nombre_organismo"}
        cte, p = self._lic(f)
        return self.q(
            f"""{cte}
            select {dim} grupo, count(*) n, avg(es_oferente_unico::int) pct_unico,
                   median(n_proveedores_oferentes) mediana_oferentes
            from l where {self._ADJ_CON_OFERTAS} and {dim} is not null
            group by 1 having count(*) >= {int(min_n)} order by pct_unico desc""",
            p,
        )

    # ---------- 2. precio ----------

    _CON_RAZON = f"estado_grupo = 'Adjudicada' and razon_adjudicado_estimado >= {RAZON_PRECIO_UNITARIO}"

    def precio_kpis(self, f: Filtros) -> dict:
        cte, p = self._lic(f)
        return (
            self.q(
                f"""{cte}
                select count(*) n,
                       (select avg((razon_adjudicado_estimado < {RAZON_PRECIO_UNITARIO})::int) from l
                        where estado_grupo = 'Adjudicada' and razon_adjudicado_estimado is not null
                       ) pct_precio_unitario,
                       median(razon_adjudicado_estimado) mediana,
                       avg((razon_adjudicado_estimado > 1)::int) pct_sobre,
                       avg((razon_adjudicado_estimado > {RAZON_SOBRE_ESTIMADO})::int) pct_sobre_20,
                       avg((razon_adjudicado_estimado < 0.5)::int) pct_bajo_mitad
                from l where {self._CON_RAZON}""",
                p,
            )
            .iloc[0]
            .to_dict()
        )

    def precio_histograma(self, f: Filtros) -> pd.DataFrame:
        cte, p = self._lic(f)
        return self.q(
            f"""{cte}
            select least(floor(razon_adjudicado_estimado * 10) / 10, 2.0) desde, count(*) n
            from l where {self._CON_RAZON}
            group by 1 order by 1""",
            p,
        )

    def precio_vs_competencia(self, f: Filtros) -> pd.DataFrame:
        cte, p = self._lic(f)
        return self.q(
            f"""{cte}
            select least(n_proveedores_oferentes, 10) oferentes, count(*) n,
                   median(razon_adjudicado_estimado) mediana,
                   quantile_cont(razon_adjudicado_estimado, 0.25) p25,
                   quantile_cont(razon_adjudicado_estimado, 0.75) p75
            from l where {self._CON_RAZON} and n_proveedores_oferentes > 0
            group by 1 having count(*) >= {MIN_GRUPO} order by 1""",
            p,
        )

    def precio_por_tipo(self, f: Filtros) -> pd.DataFrame:
        cte, p = self._lic(f)
        return self.q(
            f"""{cte}
            select tipo_descripcion grupo, min(tipo_orden) orden, count(*) n,
                   median(razon_adjudicado_estimado) mediana,
                   avg((razon_adjudicado_estimado > 1)::int) pct_sobre
            from l where {self._CON_RAZON}
            group by 1 having count(*) >= {MIN_GRUPO} order by orden""",
            p,
        )

    # ---------- 3. concentración ----------

    def _adj_clp(self, f: Filtros) -> tuple[str, list]:
        cte, p = self._lic(f)
        return (
            f"""{cte},
            a as (
                select l.codigo_organismo, l.nombre_organismo, a.codigo_proveedor, a.codigo_externo,
                       a.monto_adjudicado monto
                from adjudicaciones a join l using (codigo_externo)
                where a.moneda = 'CLP' and a.monto_adjudicado > 0
            )""",
            p,
        )

    def concentracion_organismos(self, f: Filtros, min_lic: int = MIN_GRUPO) -> pd.DataFrame:
        """Por organismo: participación del proveedor principal e índice HHI (0–10.000)."""
        cte, p = self._adj_clp(f)
        return self.q(
            f"""{cte},
            op as (
                select codigo_organismo, any_value(nombre_organismo) nombre_organismo, codigo_proveedor,
                       sum(monto) monto, count(distinct codigo_externo) lic
                from a group by 1, 3
            ),
            org as (
                select codigo_organismo, any_value(nombre_organismo) nombre_organismo,
                       sum(monto) monto_total, count(*) n_proveedores, sum(lic) lic_proveedor,
                       max(monto) monto_top
                from op group by 1
            ),
            lic as (select codigo_organismo, count(distinct codigo_externo) n_lic from a group by 1)
            select org.codigo_organismo, org.nombre_organismo, org.monto_total, org.n_proveedores, lic.n_lic,
                   org.monto_top / org.monto_total share_top,
                   (select sum(power(op.monto / org.monto_total, 2)) * 10000
                    from op where op.codigo_organismo = org.codigo_organismo) hhi,
                   (select p.nombre_proveedor from op join proveedores p using (codigo_proveedor)
                    where op.codigo_organismo = org.codigo_organismo order by op.monto desc limit 1) proveedor_top
            from org join lic using (codigo_organismo)
            where lic.n_lic >= {int(min_lic)}
            order by hhi desc""",
            p,
        )

    def concentracion_kpis(self, f: Filtros) -> dict:
        orgs = self.concentracion_organismos(f)
        if orgs.empty:
            return {"n": 0}
        return {
            "n": len(orgs),
            "pct_alta": float((orgs["hhi"] > 2500).mean()),
            "mediana_share_top": float(orgs["share_top"].median()),
            "mediana_hhi": float(orgs["hhi"].median()),
        }

    def top_proveedores(self, f: Filtros, n: int = 25) -> pd.DataFrame:
        cte, p = self._adj_clp(f)
        return self.q(
            f"""{cte},
            tot as (select sum(monto) t from a)
            select a.codigo_proveedor, any_value(pr.nombre_proveedor) proveedor, any_value(pr.rut_proveedor) rut,
                   sum(monto) monto, sum(monto) / any_value(tot.t) participacion,
                   count(distinct codigo_externo) licitaciones, count(distinct codigo_organismo) organismos
            from a cross join tot left join proveedores pr using (codigo_proveedor)
            group by 1 order by monto desc limit {int(n)}""",
            p,
        )

    def concentracion_mercado(self, f: Filtros) -> dict:
        cte, p = self._adj_clp(f)
        return (
            self.q(
                f"""{cte},
                prov as (select codigo_proveedor, sum(monto) m from a group by 1),
                r as (select m, row_number() over (order by m desc) rk, sum(m) over () t from prov)
                select count(*) proveedores,
                       sum(m) filter (where rk <= 10) / any_value(t) share_top10,
                       sum(m) filter (where rk <= ceil(0.01 * (select count(*) from prov))) / any_value(t) share_top1pct
                from r""",
                p,
            )
            .iloc[0]
            .to_dict()
        )

    # ---------- 4. proceso ----------

    def _maduras(self, f: Filtros) -> tuple[str, list]:
        cte, p = self._lic(f)
        return (
            f"""{cte},
            m as (select * from l where fecha_cierre <= date '{self.corte}' - interval {DIAS_MADUREZ} day)""",
            p,
        )

    def proceso_kpis(self, f: Filtros) -> dict:
        cte, p = self._maduras(f)
        r = self.q(
            f"""{cte}
            select count(*) n,
                   avg((estado_grupo = 'Adjudicada')::int) pct_adjudicada,
                   avg((estado_grupo = 'Desierta')::int) pct_desierta,
                   avg((estado_grupo = 'Revocada')::int) pct_revocada,
                   avg((estado_grupo in ('Cerrada', 'Suspendida', 'Publicada'))::int) pct_sin_resolver,
                   median(dias_publicacion_cierre) mediana_dias_oferta,
                   median(dias_cierre_adjudicacion) mediana_dias_adjudicar
            from m""",
            p,
        ).iloc[0]
        return r.to_dict()

    def proceso_por_tipo(self, f: Filtros) -> pd.DataFrame:
        cte, p = self._maduras(f)
        return self.q(
            f"""{cte}
            select tipo_descripcion grupo, min(tipo_orden) orden, count(*) n,
                   avg((estado_grupo = 'Adjudicada')::int) adjudicada,
                   avg((estado_grupo = 'Desierta')::int) desierta,
                   avg((estado_grupo = 'Revocada')::int) revocada,
                   avg((estado_grupo in ('Cerrada', 'Suspendida', 'Publicada'))::int) sin_resolver,
                   median(dias_publicacion_cierre) dias_oferta,
                   median(dias_cierre_adjudicacion) dias_adjudicar
            from m group by 1 having count(*) >= {MIN_GRUPO} order by orden""",
            p,
        )

    def proceso_mensual(self, f: Filtros) -> pd.DataFrame:
        cte, p = self._lic(f)
        return self.q(
            f"""{cte}
            select mes_publicacion mes,
                   median(dias_cierre_adjudicacion) dias_adjudicar,
                   avg((estado_grupo = 'Desierta')::int) pct_desierta,
                   count(*) n
            from l group by 1 order by 1""",
            p,
        )

    # ---------- señales de alerta ----------
    # Seis señales por licitación adjudicada, ponderadas en un puntaje 0–100 (calculado en dbt,
    # int_licitacion_senales). Una señal no prueba una irregularidad: es un motivo para revisar.

    def _sql_senales(self) -> str:
        return ", ".join(f"avg({c}::int) {c}" for c, _, _ in SENALES)

    def alertas_resumen(self, f: Filtros) -> dict:
        """Niveles de riesgo y prevalencia de cada señal entre las adjudicadas."""
        cte, p = self._lic(f)
        r = self.q(
            f"""{cte}
            select count(*) n,
                   count(*) filter (where puntaje_riesgo >= {RIESGO_ALTO}) alto,
                   count(*) filter (where puntaje_riesgo >= {RIESGO_MEDIO} and puntaje_riesgo < {RIESGO_ALTO}) medio,
                   count(*) filter (where puntaje_riesgo > 0 and puntaje_riesgo < {RIESGO_MEDIO}) bajo,
                   count(*) filter (where puntaje_riesgo = 0) sin,
                   sum(monto_adjudicado) filter (where puntaje_riesgo >= {RIESGO_ALTO} and moneda_adjudicada = 'CLP')
                       monto_alto,
                   {self._sql_senales()}
            from l where estado_grupo = 'Adjudicada'""",
            p,
        ).iloc[0]
        return r.to_dict()

    def alertas(self, f: Filtros, min_puntaje: int = RIESGO_ALTO, limite: int = 500) -> pd.DataFrame:
        cte, p = self._lic(f)
        cols = ", ".join(c for c, _, _ in SENALES)
        return self.q(
            f"""{cte}
            select codigo_externo, nombre, nombre_organismo, tipo_descripcion, fecha_publicacion,
                   puntaje_riesgo, {cols}, n_proveedores_oferentes, dias_publicacion_cierre,
                   monto_estimado, monto_adjudicado, moneda_adjudicada, razon_adjudicado_estimado,
                   razon_sobre_mas_barata, link
            from l
            where estado_grupo = 'Adjudicada' and puntaje_riesgo >= {int(min_puntaje)}
            order by puntaje_riesgo desc, monto_adjudicado desc nulls last
            limit {int(limite)}""",
            p,
        )

    def _adj_riesgo(self, f: Filtros) -> tuple[str, list]:
        """Adjudicaciones en CLP de licitaciones adjudicadas, con el puntaje de la licitación."""
        cte, p = self._lic(f)
        cols = ", ".join(f"l.{c}" for c, _, _ in SENALES)
        return (
            f"""{cte},
            a as (
                select a.codigo_proveedor, a.codigo_externo, a.monto_adjudicado monto,
                       l.codigo_organismo, l.nombre_organismo, l.puntaje_riesgo, {cols}
                from adjudicaciones a join l using (codigo_externo)
                where a.moneda = 'CLP' and a.monto_adjudicado > 0 and l.estado_grupo = 'Adjudicada'
            )""",
            p,
        )

    def proveedores_riesgo(self, f: Filtros, min_lic: int = 3, limite: int | None = None) -> pd.DataFrame:
        """Una fila por proveedor: cuánto gana, con qué señales, y de cuánto depende de un organismo.

        - dependencia: parte de los ingresos del proveedor que viene de su organismo principal.
        - captura: parte del gasto de ese organismo que se lleva el proveedor.
        - max_unico_org: máximo de licitaciones ganadas sin competencia en un mismo organismo."""
        cte, p = self._adj_riesgo(f)
        señales = ", ".join(f"sum({c}::int) n_{c[2:]}" for c, _, _ in SENALES)
        lim = f"limit {int(limite)}" if limite else ""
        return self.q(
            f"""{cte},
            org_total as (select codigo_organismo, sum(monto) total from a group by 1),
            po as (
                select codigo_proveedor, codigo_organismo, any_value(nombre_organismo) nombre_organismo,
                       sum(monto) monto, count(distinct codigo_externo) filter (where s_oferente_unico) unico
                from a group by 1, 2
            ),
            top_org as (
                select distinct on (codigo_proveedor) codigo_proveedor, codigo_organismo, nombre_organismo,
                       monto monto_org
                from po order by codigo_proveedor, monto desc, codigo_organismo
            ),
            lic as (
                select distinct codigo_proveedor, codigo_externo, puntaje_riesgo,
                       {", ".join(c for c, _, _ in SENALES)}
                from a
            ),
            pr as (
                select codigo_proveedor, count(*) n_lic, avg(puntaje_riesgo) puntaje_medio,
                       count(*) filter (where puntaje_riesgo >= {RIESGO_ALTO}) n_alto,
                       avg(s_oferente_unico::int) pct_unico, {señales}
                from lic group by 1
            ),
            m as (
                select codigo_proveedor, sum(monto) monto, count(distinct codigo_organismo) n_org,
                       sum(monto) filter (where puntaje_riesgo >= {RIESGO_ALTO}) monto_alto
                from a group by 1
            )
            select pr.codigo_proveedor, pv.nombre_proveedor proveedor, pv.rut_proveedor rut,
                   pr.n_lic, m.monto, m.n_org, pr.puntaje_medio, pr.n_alto, coalesce(m.monto_alto, 0) monto_alto,
                   pr.pct_unico, t.nombre_organismo organismo_principal,
                   t.monto_org / m.monto dependencia, t.monto_org / ot.total captura,
                   (select max(unico) from po where po.codigo_proveedor = pr.codigo_proveedor) max_unico_org,
                   pv.n_licitaciones_ofertadas n_ofertadas,
                   (select count(*) from pares where pares.ganador = pr.codigo_proveedor) n_acompanantes,
                   {", ".join(f"pr.n_{c[2:]}" for c, _, _ in SENALES)}
            from pr join m using (codigo_proveedor)
            join top_org t using (codigo_proveedor)
            join org_total ot on ot.codigo_organismo = t.codigo_organismo
            left join proveedores pv using (codigo_proveedor)
            where pr.n_lic >= {int(min_lic)}
            order by monto_alto desc, pr.n_alto desc, m.monto desc
            {lim}""",
            p,
        )

    def organismos_riesgo(self, f: Filtros, min_lic: int = MIN_GRUPO) -> pd.DataFrame:
        cte, p = self._lic(f)
        return self.q(
            f"""{cte},
            o as (
                select codigo_organismo, any_value(nombre_organismo) organismo, count(*) n,
                       avg(puntaje_riesgo) puntaje_medio,
                       avg((puntaje_riesgo >= {RIESGO_ALTO})::int) pct_alto,
                       count(*) filter (where puntaje_riesgo >= {RIESGO_ALTO}) n_alto,
                       avg(s_oferente_unico::int) pct_unico,
                       avg(s_competencia_descalificada::int) pct_descalificada,
                       coalesce(sum(monto_adjudicado) filter (
                           where puntaje_riesgo >= {RIESGO_ALTO} and moneda_adjudicada = 'CLP'
                       ), 0) monto_alto
                from l where estado_grupo = 'Adjudicada' group by 1
            )
            select * from o where n >= {int(min_lic)} order by pct_alto desc, n desc""",
            p,
        )

    def proveedor(self, codigo: str, f: Filtros) -> dict[str, pd.DataFrame]:
        """Ficha de un proveedor: sus licitaciones ganadas, organismos y acompañantes."""
        cte, p = self._adj_riesgo(f)
        lic = self.q(
            f"""{cte}
            select a.codigo_externo, l.nombre, a.nombre_organismo, l.fecha_publicacion, a.puntaje_riesgo,
                   {", ".join(f"a.{c}" for c, _, _ in SENALES)}, l.n_proveedores_oferentes, a.monto, l.link
            from a join l using (codigo_externo)
            where a.codigo_proveedor = ?
            order by a.puntaje_riesgo desc, a.monto desc""",
            [*p, codigo],
        )
        orgs = self.q(
            f"""{cte},
            ot as (select codigo_organismo, sum(monto) total from a group by 1)
            select a.nombre_organismo organismo, count(distinct codigo_externo) n_lic, sum(monto) monto,
                   avg(s_oferente_unico::int) pct_unico, sum(monto) / any_value(ot.total) captura
            from a join ot using (codigo_organismo)
            where a.codigo_proveedor = ?
            group by a.codigo_organismo, a.nombre_organismo order by monto desc""",
            [*p, codigo],
        )
        pares = self.q(
            """select pv.nombre_proveedor acompanante, juntos, gana_ganador from pares
               left join proveedores pv on pv.codigo_proveedor = pares.acompanante
               where ganador = ? order by juntos desc""",
            [codigo],
        )
        return {"licitaciones": lic, "organismos": orgs, "acompanantes": pares}
