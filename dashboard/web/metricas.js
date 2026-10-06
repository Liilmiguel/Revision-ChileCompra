/* Métricas de las 4 preguntas, en el navegador. Port de src/observatorio/metricas.py:
 * mismas definiciones y umbrales (los trae meta.json). verificar.mjs compara ambos. */
(function (root) {
  "use strict";
  const NA16 = -32768;

  // Los grupos "por tipo" usan la descripción (como tipo_descripcion en Python): varios
  // códigos poco frecuentes comparten "Otro".
  function cargar(meta, licBuf, adjBuf, catalogos) {
    const T = { uint8: Uint8Array, uint16: Uint16Array, int16: Int16Array, float32: Float32Array, float64: Float64Array };
    const c = {};
    for (const { col, dtype, offset } of meta.layout) c[col] = new T[dtype](licBuf, offset, meta.n);
    const m = meta.n_adj;
    return {
      n: meta.n,
      k: meta.constantes,
      tipoDesc: catalogos.tipos.map((t) => t[1]),
      c,
      adj: {
        lic: new Uint32Array(adjBuf, 0, m),
        prov: new Uint32Array(adjBuf, 4 * m, m),
        monto: new Float32Array(adjBuf, 8 * m, m),
      },
    };
  }

  // Filtros: { desde, hasta (meses desde 2024-01), tipo, region, sector, org (índices o null) }
  function mascara(d, f) {
    const { mes, tipo, region, sector, org } = d.c;
    const out = new Uint8Array(d.n);
    for (let i = 0; i < d.n; i++) {
      out[i] =
        mes[i] >= f.desde &&
        mes[i] <= f.hasta &&
        (f.tipo == null || tipo[i] === f.tipo) &&
        (f.region == null || region[i] === f.region) &&
        (f.sector == null || sector[i] === f.sector) &&
        (f.org == null || org[i] === f.org)
          ? 1
          : 0;
    }
    return out;
  }

  // quantile_cont de DuckDB: interpolación lineal.
  function cuantil(sorted, q) {
    if (!sorted.length) return null;
    const pos = q * (sorted.length - 1);
    const lo = Math.floor(pos);
    const hi = Math.ceil(pos);
    return sorted[lo] + (sorted[hi] - sorted[lo]) * (pos - lo);
  }
  const ordenar = (arr) => Float64Array.from(arr).sort();
  const mediana = (arr) => cuantil(ordenar(arr), 0.5);

  const ADJ = 0; // índice de "Adjudicada" en meta/catalogos.estados
  const DES = 1;
  const REV = 2;

  function resumen(d, mk) {
    const { estado, monto, org } = d.c;
    let n = 0, adj = 0, total = 0;
    const orgs = new Set();
    for (let i = 0; i < d.n; i++) {
      if (!mk[i]) continue;
      n++;
      if (estado[i] === ADJ) adj++;
      if (!Number.isNaN(monto[i])) total += monto[i];
      orgs.add(org[i]);
    }
    const provs = new Set();
    for (let j = 0; j < d.adj.lic.length; j++) if (mk[d.adj.lic[j]]) provs.add(d.adj.prov[j]);
    return { n, adjudicadas: adj, monto_clp: total, organismos: orgs.size, proveedores: provs.size };
  }

  function mensual(d, mk, nMeses) {
    const pub = new Array(nMeses).fill(0);
    const adj = new Array(nMeses).fill(0);
    const { mes, estado } = d.c;
    for (let i = 0; i < d.n; i++) {
      if (!mk[i]) continue;
      pub[mes[i]]++;
      if (estado[i] === ADJ) adj[mes[i]]++;
    }
    return { pub, adj };
  }

  // ---------- 1. competencia: adjudicadas con ofertas registradas
  function competencia(d, mk, nMeses) {
    const { estado, ofer, mes } = d.c;
    const vals = [];
    let unico = 0;
    const dist = new Array(11).fill(0); // 1..9 y 10+
    const mU = new Array(nMeses).fill(0);
    const mN = new Array(nMeses).fill(0);
    for (let i = 0; i < d.n; i++) {
      if (!mk[i] || estado[i] !== ADJ || ofer[i] === 0) continue;
      vals.push(ofer[i]);
      if (ofer[i] === 1) { unico++; mU[mes[i]]++; }
      mN[mes[i]]++;
      dist[Math.min(ofer[i], 10)]++;
    }
    const n = vals.length;
    const suma = vals.reduce((a, b) => a + b, 0);
    return {
      n,
      pct_unico: n ? unico / n : null,
      mediana_oferentes: mediana(vals),
      media_oferentes: n ? suma / n : null,
      dist: dist.slice(1),
      mensual: mN.map((v, k) => (v ? mU[k] / v : null)),
      mensual_n: mN,
    };
  }

  function competenciaPor(d, mk, col, minN) {
    const { estado, ofer } = d.c;
    const g = new Map();
    const key = col === "tipo" ? Array.from(d.c.tipo, (t) => d.tipoDesc[t]) : d.c[col];
    for (let i = 0; i < d.n; i++) {
      if (!mk[i] || estado[i] !== ADJ || ofer[i] === 0) continue;
      if (col !== "org" && col !== "tipo" && key[i] === 0) continue; // sin dato
      let e = g.get(key[i]);
      if (!e) g.set(key[i], (e = { n: 0, u: 0, v: [] }));
      e.n++;
      if (ofer[i] === 1) e.u++;
      e.v.push(ofer[i]);
    }
    return [...g.entries()]
      .filter(([, e]) => e.n >= minN)
      .map(([k, e]) => ({ grupo: k, n: e.n, pct_unico: e.u / e.n, mediana: mediana(e.v) }))
      .sort((a, b) => b.pct_unico - a.pct_unico);
  }

  // ---------- 2. precio: razón ≥ RAZON_PRECIO_UNITARIO (suministros por precio unitario fuera)
  function precio(d, mk) {
    const { estado, razon, ofer, tipo } = d.c;
    const K = d.k;
    const r = [];
    let conRazon = 0, unitario = 0, sobre = 0, sobre20 = 0, mitad = 0;
    const hist = new Array(21).fill(0);
    const porOfer = new Map();
    const porTipo = new Map();
    for (let i = 0; i < d.n; i++) {
      if (!mk[i] || estado[i] !== ADJ || Number.isNaN(razon[i])) continue;
      conRazon++;
      const x = razon[i];
      if (x < K.RAZON_PRECIO_UNITARIO) { unitario++; continue; }
      r.push(x);
      if (x > 1) sobre++;
      if (x > K.RAZON_SOBRE_ESTIMADO) sobre20++;
      if (x < 0.5) mitad++;
      hist[Math.min(Math.floor(x * 10), 20)]++;
      if (ofer[i] > 0) {
        const o = Math.min(ofer[i], 10);
        if (!porOfer.has(o)) porOfer.set(o, []);
        porOfer.get(o).push(x);
      }
      const td = d.tipoDesc[tipo[i]];
      if (!porTipo.has(td)) porTipo.set(td, { orden: tipo[i], v: [] });
      porTipo.get(td).v.push(x);
    }
    const n = r.length;
    const comp = [...porOfer.entries()]
      .filter(([, v]) => v.length >= K.MIN_GRUPO)
      .sort((a, b) => a[0] - b[0])
      .map(([o, v]) => {
        const s = ordenar(v);
        return { oferentes: o, n: v.length, mediana: cuantil(s, 0.5), p25: cuantil(s, 0.25), p75: cuantil(s, 0.75) };
      });
    const tipos = [...porTipo.entries()]
      .filter(([, e]) => e.v.length >= K.MIN_GRUPO)
      .sort((a, b) => a[1].orden - b[1].orden)
      .map(([t, e]) => ({ grupo: t, n: e.v.length, mediana: mediana(e.v), pct_sobre: e.v.filter((x) => x > 1).length / e.v.length }));
    return {
      n,
      pct_precio_unitario: conRazon ? unitario / conRazon : null,
      mediana: mediana(r),
      pct_sobre: n ? sobre / n : null,
      pct_sobre_20: n ? sobre20 / n : null,
      pct_bajo_mitad: n ? mitad / n : null,
      hist,
      comp,
      tipos,
    };
  }

  // ---------- 3. concentración (montos en CLP, sin líneas atípicas)
  function concentracion(d, mk, nombresProv) {
    const K = d.k;
    const porOrg = new Map(); // org -> { prov -> monto, lics:Set }
    const porProv = new Map(); // prov -> { m, lics:Set, orgs:Set }
    let total = 0;
    const A = d.adj;
    const org = d.c.org;
    for (let j = 0; j < A.lic.length; j++) {
      const li = A.lic[j];
      if (!mk[li]) continue;
      const m = A.monto[j];
      const o = org[li];
      const p = A.prov[j];
      total += m;
      let e = porOrg.get(o);
      if (!e) porOrg.set(o, (e = { prov: new Map(), lics: new Set() }));
      e.prov.set(p, (e.prov.get(p) || 0) + m);
      e.lics.add(li);
      let q = porProv.get(p);
      if (!q) porProv.set(p, (q = { m: 0, lics: new Set(), orgs: new Set() }));
      q.m += m;
      q.lics.add(li);
      q.orgs.add(o);
    }
    const orgs = [];
    for (const [o, e] of porOrg) {
      if (e.lics.size < K.MIN_GRUPO) continue;
      let t = 0, top = 0, topP = null;
      for (const [p, m] of e.prov) { t += m; if (m > top) { top = m; topP = p; } }
      let hhi = 0;
      for (const m of e.prov.values()) hhi += (m / t) ** 2;
      orgs.push({ org: o, monto_total: t, n_proveedores: e.prov.size, n_lic: e.lics.size, share_top: top / t, hhi: hhi * 10000, proveedor_top: nombresProv[topP][0] });
    }
    orgs.sort((a, b) => b.hhi - a.hhi);
    const provs = [...porProv.entries()].map(([p, q]) => ({ prov: p, monto: q.m, lics: q.lics.size, orgs: q.orgs.size })).sort((a, b) => b.monto - a.monto);
    const top10 = provs.slice(0, 10).reduce((a, b) => a + b.monto, 0);
    const k1 = Math.ceil(0.01 * provs.length);
    const top1 = provs.slice(0, k1).reduce((a, b) => a + b.monto, 0);
    return {
      orgs,
      kpis: orgs.length
        ? { n: orgs.length, pct_alta: orgs.filter((o) => o.hhi > 2500).length / orgs.length, mediana_share_top: mediana(orgs.map((o) => o.share_top)), mediana_hhi: mediana(orgs.map((o) => o.hhi)) }
        : { n: 0 },
      mercado: { proveedores: provs.length, share_top10: total ? top10 / total : null, share_top1pct: total ? top1 / total : null },
      top: provs.slice(0, 200).map((p) => ({ ...p, share: p.monto / total, nombre: nombresProv[p.prov][0], rut: nombresProv[p.prov][1] })),
    };
  }

  // ---------- 4. proceso: licitaciones "maduras" (cerradas hace más de DIAS_MADUREZ días)
  function proceso(d, mk, nMeses) {
    const { madura, estado, dofer, dadj, tipo, mes } = d.c;
    let n = 0;
    const cuenta = [0, 0, 0, 0];
    const vo = [], va = [];
    const porTipo = new Map();
    const mDadj = Array.from({ length: nMeses }, () => []);
    const mN = new Array(nMeses).fill(0);
    const mDes = new Array(nMeses).fill(0);
    for (let i = 0; i < d.n; i++) {
      if (!mk[i]) continue;
      mN[mes[i]]++;
      if (estado[i] === DES) mDes[mes[i]]++;
      if (dadj[i] !== NA16) mDadj[mes[i]].push(dadj[i]);
      if (!madura[i]) continue;
      n++;
      const g = estado[i] === ADJ ? 0 : estado[i] === DES ? 1 : estado[i] === REV ? 2 : 3;
      cuenta[g]++;
      if (dofer[i] !== NA16) vo.push(dofer[i]);
      if (dadj[i] !== NA16) va.push(dadj[i]);
      const td = d.tipoDesc[tipo[i]];
      let e = porTipo.get(td);
      if (!e) porTipo.set(td, (e = { orden: tipo[i], n: 0, c: [0, 0, 0, 0], vo: [], va: [] }));
      e.n++;
      e.c[g]++;
      if (dofer[i] !== NA16) e.vo.push(dofer[i]);
      if (dadj[i] !== NA16) e.va.push(dadj[i]);
    }
    return {
      n,
      pct_adjudicada: n ? cuenta[0] / n : null,
      pct_desierta: n ? cuenta[1] / n : null,
      pct_revocada: n ? cuenta[2] / n : null,
      pct_sin_resolver: n ? cuenta[3] / n : null,
      mediana_dias_oferta: mediana(vo),
      mediana_dias_adjudicar: mediana(va),
      tipos: [...porTipo.entries()]
        .filter(([, e]) => e.n >= d.k.MIN_GRUPO)
        .sort((a, b) => a[1].orden - b[1].orden)
        .map(([t, e]) => ({ grupo: t, n: e.n, adjudicada: e.c[0] / e.n, desierta: e.c[1] / e.n, revocada: e.c[2] / e.n, sin_resolver: e.c[3] / e.n, dias_oferta: mediana(e.vo), dias_adjudicar: mediana(e.va) })),
      mensual: mDadj.map((v) => mediana(v)),
      mensual_desierta: mN.map((v, k) => (v ? mDes[k] / v : null)),
    };
  }

  // ---------- señales de alerta (solo adjudicadas)
  function alertasResumen(d, mk) {
    const { estado, senales } = d.c;
    const n = [0, 0, 0, 0];
    for (let i = 0; i < d.n; i++) {
      if (!mk[i] || estado[i] !== ADJ) continue;
      const s = senales[i];
      n[(s & 1) + ((s >> 1) & 1) + ((s >> 2) & 1)]++;
    }
    return n;
  }

  const M = { cargar, mascara, cuantil, mediana, resumen, mensual, competencia, competenciaPor, precio, concentracion, proceso, alertasResumen };
  if (typeof module !== "undefined" && module.exports) module.exports = M;
  else root.Metricas = M;
})(typeof self !== "undefined" ? self : this);
