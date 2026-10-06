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

  // ---------- señales de alerta (solo adjudicadas). Bits de `senal` en el orden de meta.SENALES:
  // 0 oferente único, 1 competencia descalificada, 2 sobre la oferta más barata, 3 sobre estimado,
  // 4 plazo corto, 5 precio sobre referencia. `puntaje` es la suma ponderada (dbt).
  function alertasResumen(d, mk) {
    const { estado, senal, puntaje, monto } = d.c;
    const K = d.k;
    const ns = K.SENALES.length;
    const prev = new Array(ns).fill(0);
    let n = 0, alto = 0, medio = 0, bajo = 0, sin = 0, montoAlto = 0;
    for (let i = 0; i < d.n; i++) {
      if (!mk[i] || estado[i] !== ADJ) continue;
      n++;
      const p = puntaje[i];
      if (p >= K.RIESGO_ALTO) { alto++; if (!Number.isNaN(monto[i])) montoAlto += monto[i]; }
      else if (p >= K.RIESGO_MEDIO) medio++;
      else if (p > 0) bajo++;
      else sin++;
      for (let b = 0; b < ns; b++) if (senal[i] & (1 << b)) prev[b]++;
    }
    return { n, alto, medio, bajo, sin, monto_alto: montoAlto, prev: prev.map((v) => (n ? v / n : null)) };
  }

  // Proveedores: adjudicaciones en CLP de licitaciones adjudicadas (como _adj_riesgo en Python).
  function proveedoresRiesgo(d, mk, minLic, pares) {
    const { estado, puntaje, senal, org } = d.c;
    const A = d.adj;
    const K = d.k;
    const ns = K.SENALES.length;
    const orgTotal = new Map();
    const P = new Map(); // prov -> { lics:Map(lic->1), monto, montoAlto, orgs:Map(org->{m, unico:Set}) }
    for (let j = 0; j < A.lic.length; j++) {
      const li = A.lic[j];
      if (!mk[li] || estado[li] !== ADJ) continue;
      const m = A.monto[j], o = org[li], pv = A.prov[j];
      orgTotal.set(o, (orgTotal.get(o) || 0) + m);
      let e = P.get(pv);
      if (!e) P.set(pv, (e = { lics: new Set(), monto: 0, montoAlto: 0, orgs: new Map() }));
      e.lics.add(li);
      e.monto += m;
      if (puntaje[li] >= K.RIESGO_ALTO) e.montoAlto += m;
      let q = e.orgs.get(o);
      if (!q) e.orgs.set(o, (q = { m: 0, unico: new Set() }));
      q.m += m;
      if (senal[li] & 1) q.unico.add(li);
    }
    const acomp = new Map();
    for (const [g] of pares) acomp.set(g, (acomp.get(g) || 0) + 1);
    const out = [];
    for (const [pv, e] of P) {
      if (e.lics.size < minLic) continue;
      let suma = 0, alto = 0, unico = 0;
      const cuenta = new Array(ns).fill(0);
      for (const li of e.lics) {
        suma += puntaje[li];
        if (puntaje[li] >= K.RIESGO_ALTO) alto++;
        if (senal[li] & 1) unico++;
        for (let b = 0; b < ns; b++) if (senal[li] & (1 << b)) cuenta[b]++;
      }
      let top = null, topM = -1, maxUnico = 0;
      for (const [o, q] of e.orgs) {
        if (q.m > topM || (q.m === topM && o < top)) { topM = q.m; top = o; }
        if (q.unico.size > maxUnico) maxUnico = q.unico.size;
      }
      out.push({
        prov: pv, n_lic: e.lics.size, monto: e.monto, n_org: e.orgs.size, puntaje_medio: suma / e.lics.size,
        n_alto: alto, monto_alto: e.montoAlto, pct_unico: unico / e.lics.size, org_principal: top,
        dependencia: topM / e.monto, captura: topM / orgTotal.get(top), max_unico_org: maxUnico,
        n_acompanantes: acomp.get(pv) || 0, senales: cuenta,
      });
    }
    out.sort((a, b) => b.monto_alto - a.monto_alto || b.n_alto - a.n_alto || b.monto - a.monto);
    return out;
  }

  function organismosRiesgo(d, mk, minLic) {
    const { estado, puntaje, senal, org, monto } = d.c;
    const K = d.k;
    const G = new Map();
    for (let i = 0; i < d.n; i++) {
      if (!mk[i] || estado[i] !== ADJ) continue;
      let e = G.get(org[i]);
      if (!e) G.set(org[i], (e = { n: 0, suma: 0, alto: 0, unico: 0, desc: 0, montoAlto: 0 }));
      e.n++;
      e.suma += puntaje[i];
      if (puntaje[i] >= K.RIESGO_ALTO) { e.alto++; if (!Number.isNaN(monto[i])) e.montoAlto += monto[i]; }
      if (senal[i] & 1) e.unico++;
      if (senal[i] & 2) e.desc++;
    }
    return [...G.entries()]
      .filter(([, e]) => e.n >= minLic)
      .map(([o, e]) => ({ org: o, n: e.n, puntaje_medio: e.suma / e.n, pct_alto: e.alto / e.n, n_alto: e.alto, pct_unico: e.unico / e.n, pct_descalificada: e.desc / e.n, monto_alto: e.montoAlto }))
      .sort((a, b) => b.pct_alto - a.pct_alto || b.n - a.n);
  }

  // Ficha de un proveedor: sus licitaciones adjudicadas (en CLP) y los organismos que le compran.
  function fichaProveedor(d, mk, prov) {
    const { estado, org, mes } = d.c;
    const A = d.adj;
    const orgTotal = new Map();
    const lics = new Map();
    const orgs = new Map();
    for (let j = 0; j < A.lic.length; j++) {
      const li = A.lic[j];
      if (!mk[li] || estado[li] !== ADJ) continue;
      const o = org[li];
      orgTotal.set(o, (orgTotal.get(o) || 0) + A.monto[j]);
      if (A.prov[j] !== prov) continue;
      lics.set(li, (lics.get(li) || 0) + A.monto[j]);
      let q = orgs.get(o);
      if (!q) orgs.set(o, (q = { lics: new Set(), m: 0, unico: 0 }));
      if (!q.lics.has(li) && d.c.senal[li] & 1) q.unico++;
      q.lics.add(li);
      q.m += A.monto[j];
    }
    const porMes = new Map();
    for (const [li, m] of lics) porMes.set(mes[li], (porMes.get(mes[li]) || 0) + m);
    return {
      lics: [...lics.entries()].map(([li, m]) => ({ li, monto: m })),
      orgs: [...orgs.entries()].map(([o, q]) => ({ org: o, n_lic: q.lics.size, monto: q.m, pct_unico: q.unico / q.lics.size, captura: q.m / orgTotal.get(o) })).sort((a, b) => b.monto - a.monto),
      porMes,
    };
  }

  // ---------- en curso (vivo.json): licitaciones abiertas y cerradas en evaluación.
  // Se cruzan con el historial completo (sin filtros): plazos típicos por tipo, organismos y
  // proveedores con riesgo alto, y pares de acompañantes. Pesos en el orden de VIVO_SENALES.
  const VIVO_SENALES = [
    ["unico", "Oferente único", 25],
    ["acomp", "Oferta junto a un acompañante habitual del mismo proveedor", 20],
    ["sobre", "Todas las ofertas más de 20 % sobre lo estimado", 15],
    ["tramo", "Monto estimado sobre el tramo legal de su tipo (procedimiento más corto que el que corresponde)", 15],
    ["plazo", "Plazo para ofertar en el 10 % más corto de su tipo", 10],
    ["org", "Organismo con historial de riesgo alto", 10],
    ["prov", "Oferente con historial de riesgo alto", 10],
  ];
  // Organismo / proveedor "con historial": 3+ licitaciones de riesgo alto y una tasa de riesgo
  // alto de al menos 3 veces la nacional (organismos) o 10 % de sus ganadas (proveedores).
  const HIST_MIN_ALTO = 3;
  const HIST_ORG_VECES = 3;
  const HIST_PROV_PCT = 0.1;

  function historialVivo(d, cat, pares) {
    const todo = new Uint8Array(d.n).fill(1);
    const K = d.k;
    const dias = new Map();
    for (let i = 0; i < d.n; i++) {
      if (d.c.dofer[i] === NA16) continue;
      const t = cat.tipos[d.c.tipo[i]][0];
      if (!dias.has(t)) dias.set(t, []);
      dias.get(t).push(d.c.dofer[i]);
    }
    const p10 = new Map([...dias].filter(([, v]) => v.length >= K.MIN_GRUPO).map(([t, v]) => [t, cuantil(ordenar(v), 0.1)]));
    const a = alertasResumen(d, todo);
    const tasa = a.n ? a.alto / a.n : 0;
    const orgs = new Map();
    for (const r of organismosRiesgo(d, todo, 1)) {
      if (r.n_alto >= HIST_MIN_ALTO && r.pct_alto >= HIST_ORG_VECES * tasa) orgs.set(cat.organismos[r.org][0], r);
    }
    const provIdx = new Map(cat.proveedores.map((p, i) => [p[3], i]));
    const provs = new Map();
    for (const r of proveedoresRiesgo(d, todo, 1, pares)) provs.set(r.prov, r);
    const acomp = new Map(); // ganador (índice) -> Map(código acompañante -> [nombre, juntos])
    for (const [g, n, j, , c] of pares) {
      if (!acomp.has(g)) acomp.set(g, new Map());
      acomp.get(g).set(c, [n, j]);
    }
    return { p10, tasa, orgs, provIdx, provs, acomp, nombres: cat.proveedores };
  }

  // Estimado creíble (como int_linea_adjudicada): bajo $1 millón suele ser simbólico ($1).
  const ESTIMADO_MIN = 1e6;
  const nf = (x, d = 0) => x.toLocaleString("es-CL", { maximumFractionDigits: d });
  const diasEntre = (a, b) => (Date.parse(b.slice(0, 10)) - Date.parse(a.slice(0, 10))) / 864e5;

  // Señales de una licitación en curso. `ofertas`: arreglos con campos `campos` (vivo.json),
  // o null en las abiertas (las ofertas son secretas hasta la apertura).
  function evaluarVivo(d, H, lic, ofertas) {
    const K = d.k;
    const s = [];
    const tope = K.TOPES_UTM[lic.tipo];
    if (lic.moneda === "CLP" && tope && lic.estimado > 1.5 * tope * K.UTM_CLP)
      s.push(["tramo", `estimado ${nf(lic.estimado / K.UTM_CLP)} UTM; su tipo (${lic.tipo}) es para menos de ${nf(tope)} UTM`]);
    const p10 = H.p10.get(lic.tipo);
    if (lic.publicada && lic.cierre && p10 != null) {
      const dd = Math.round(diasEntre(lic.publicada, lic.cierre));
      if (dd < p10) s.push(["plazo", `${dd} días para ofertar; el 10 % más corto de su tipo es menos de ${Math.round(p10)}`]);
    }
    const o = H.orgs.get(lic.org);
    if (o) s.push(["org", `${nf(100 * o.pct_alto, 1)} % de sus adjudicadas con riesgo alto (${o.n_alto}); país: ${nf(100 * H.tasa, 1)} %`]);
    let baja = null;
    if (ofertas) {
      const validas = ofertas.filter((x) => x[1] > 0);
      if (ofertas.length === 1) s.push(["unico", "una sola oferta"]);
      if (lic.moneda === "CLP" && lic.estimado >= ESTIMADO_MIN && validas.length) {
        const min = Math.min(...validas.map((x) => x[1]));
        if (min > K.RAZON_SOBRE_ESTIMADO * lic.estimado) s.push(["sobre", `la oferta más baja es ${nf((100 * min) / lic.estimado)} % del estimado`]);
      }
      const codigos = new Set(ofertas.map((x) => x[0]));
      const juntos = [];
      const historial = [];
      for (const x of ofertas) {
        const i = H.provIdx.get(x[0]);
        if (i == null) continue;
        for (const [c, [n, j]] of H.acomp.get(i) || [])
          if (codigos.has(c)) juntos.push(`${H.nombres[i][0].trim()} con ${n.trim()}: ${j} veces juntos antes, sin que ${n.trim()} le ganara`);
        const r = H.provs.get(i);
        if (r && r.n_alto >= HIST_MIN_ALTO && r.n_alto / r.n_lic >= HIST_PROV_PCT) historial.push(i);
      }
      if (juntos.length) s.push(["acomp", juntos.join("; ")]);
      if (historial.length) s.push(["prov", `${historial.length} oferente(s)`, historial]);
      for (const x of ofertas) {
        if (x[5] === "posible_error") baja = "posible_error";
        else if (x[5] === "muy_baja" && baja !== "posible_error") baja = "muy_baja";
      }
    }
    const peso = new Map(VIVO_SENALES.map(([k, , w]) => [k, w]));
    const puntaje = s.reduce((a, [k]) => a + peso.get(k), 0);
    return { puntaje, senales: s, baja };
  }

  const M = { cargar, mascara, cuantil, mediana, resumen, mensual, competencia, competenciaPor, precio, concentracion, proceso, alertasResumen, proveedoresRiesgo, organismosRiesgo, fichaProveedor, VIVO_SENALES, historialVivo, evaluarVivo };
  if (typeof module !== "undefined" && module.exports) module.exports = M;
  else root.Metricas = M;
})(typeof self !== "undefined" ? self : this);
