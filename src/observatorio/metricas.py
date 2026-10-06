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
        for name in ("licitaciones", "adjudicaciones", "proveedores"):
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

    def alertas(self, f: Filtros, limite: int = 500) -> pd.DataFrame:
        """Licitaciones adjudicadas con señales de riesgo. Una señal no es una irregularidad:
        es un motivo para mirar el expediente."""
        cte, p = self._lic(f)
        return self.q(
            f"""{cte},
            p10 as (
                select tipo, quantile_cont(dias_publicacion_cierre, 0.10) p10
                from licitaciones where dias_publicacion_cierre >= 0 group by 1
            ),
            s as (
                select l.*,
                       coalesce(es_oferente_unico, false) s_oferente_unico,
                       coalesce(razon_adjudicado_estimado > {RAZON_SOBRE_ESTIMADO}, false) s_sobre_estimado,
                       coalesce(dias_publicacion_cierre < p10.p10, false) s_plazo_corto
                from l left join p10 using (tipo)
                where estado_grupo = 'Adjudicada'
            )
            select codigo_externo, nombre, nombre_organismo, tipo_descripcion, fecha_publicacion,
                   dias_publicacion_cierre, n_proveedores_oferentes, monto_estimado, monto_adjudicado,
                   moneda_adjudicada, razon_adjudicado_estimado,
                   s_oferente_unico, s_sobre_estimado, s_plazo_corto,
                   s_oferente_unico::int + s_sobre_estimado::int + s_plazo_corto::int senales, link
            from s
            where s_oferente_unico or s_sobre_estimado or s_plazo_corto
            order by senales desc, monto_adjudicado desc nulls last
            limit {int(limite)}""",
            p,
        )

    def alertas_resumen(self, f: Filtros) -> pd.DataFrame:
        cte, p = self._lic(f)
        return self.q(
            f"""{cte},
            p10 as (
                select tipo, quantile_cont(dias_publicacion_cierre, 0.10) p10
                from licitaciones where dias_publicacion_cierre >= 0 group by 1
            ),
            s as (
                select coalesce(es_oferente_unico, false)::int
                     + coalesce(razon_adjudicado_estimado > {RAZON_SOBRE_ESTIMADO}, false)::int
                     + coalesce(dias_publicacion_cierre < p10.p10, false)::int senales
                from l left join p10 using (tipo)
                where estado_grupo = 'Adjudicada'
            )
            select senales, count(*) n from s group by 1 order by 1""",
            p,
        )
