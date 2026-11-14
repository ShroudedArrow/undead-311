// REQ-WEB-DATA.3, REQ-WEB-CHARTS, REQ-WEB-METHODS, REQ-WEB-DEATHS: FIXTURE stand-ins for the engine's statistics files
// (survival, funnel, groups, excess, temporary_fixes, exclusions, bulk_closures) until the durability-stats export exists.
// They are NOT detector output. They are computed from the same crude pairs as the other fixtures with textbook formulas
// (Kaplan-Meier with Greenwood intervals, beta-binomial shrinkage, exact binomial funnel limits), so every panel shows
// realistic shapes and the files follow /schemas. Deterministic: no clock, no RNG. data_version starts with "fixture-".

const DAY = 86400000;
const HORIZON = 90;
const round = (x, n = 4) => Math.round(x * 10 ** n) / 10 ** n;
const clamp01 = (x) => Math.min(1, Math.max(0, x));
// the two systems name two departments differently (UX-11); the fixture groups them under the legacy code
const DEPT = { "Public Works Department (PWD)": "PWDx", "Boston Transportation Department (BTD)": "BTDT" };
const canonDept = (d) => (d ? (DEPT[d] ?? d) : null);
const byName = (a, b) => (a < b ? -1 : a > b ? 1 : 0);

/** Natural log of the gamma function (Lanczos approximation, g = 7). */
export function lgamma(z) {
  const g = [0.99999999999980993, 676.5203681218851, -1259.1392167224028, 771.32342877765313, -176.61502916214059, 12.507343278686905, -0.13857109526572012, 9.9843695780195716e-6, 1.5056327351493116e-7];
  if (z < 0.5) return Math.log(Math.PI / Math.sin(Math.PI * z)) - lgamma(1 - z);
  z -= 1;
  let x = g[0];
  for (let i = 1; i < 9; i++) x += g[i] / (z + i);
  const t = z + 7.5;
  return 0.5 * Math.log(2 * Math.PI) + (z + 0.5) * Math.log(t) - t + Math.log(x);
}

/** Smallest k with P(X <= k) >= q for X ~ Binomial(n, p). */
export function binomQuantile(n, p, q) {
  if (p <= 0) return 0;
  if (p >= 1) return n;
  const lp = Math.log(p), lq = Math.log(1 - p), lnf = lgamma(n + 1);
  let cdf = 0;
  for (let k = 0; k <= n; k++) {
    cdf += Math.exp(lnf - lgamma(k + 1) - lgamma(n - k + 1) + k * lp + (n - k) * lq);
    if (cdf >= q - 1e-12) return k;
  }
  return n;
}

/** Exact binomial control limits around the citywide rate p0 for a group of n (REQ-STAT-FUNNEL.1). */
export function funnelLimits(n, p0) {
  return {
    n,
    lo95: round(binomQuantile(n, p0, 0.025) / n, 5), hi95: round(binomQuantile(n, p0, 0.975) / n, 5),
    lo998: round(binomQuantile(n, p0, 0.001) / n, 5), hi998: round(binomQuantile(n, p0, 0.999) / n, 5),
  };
}

/** The n values the funnel is drawn at: every n up to 40, then about 6% steps, always ending at the largest group. */
export function funnelNs(maxN) {
  const ns = [];
  for (let n = 1; n <= Math.min(40, maxN); n++) ns.push(n);
  for (let n = 40; n < maxN; n = Math.max(n + 1, Math.round(n * 1.06))) if (n > 40) ns.push(n);
  if (maxN > 40) ns.push(maxN);
  return [...new Set(ns)];
}

/** Kaplan-Meier on a daily grid 0..HORIZON with Greenwood 95% intervals. subjects: [{t, event}] (t in days). */
export function kaplanMeier(subjects) {
  const times = Array.from({ length: HORIZON + 1 }, (_, i) => i);
  const evTimes = [...new Set(subjects.filter((s) => s.event && s.t <= HORIZON).map((s) => s.t))].sort((a, b) => a - b);
  let s = 1, gw = 0, e = 0;
  const survival = [], lo = [], hi = [];
  for (const day of times) {
    while (e < evTimes.length && evTimes[e] <= day) {
      const t0 = evTimes[e++];
      const atRisk = subjects.filter((x) => x.t >= t0).length;
      const d = subjects.filter((x) => x.event && x.t === t0).length;
      if (atRisk > 0) {
        s *= 1 - d / atRisk;
        gw += atRisk > d ? d / (atRisk * (atRisk - d)) : 0;
      }
    }
    const se = s * Math.sqrt(gw);
    survival.push(round(s)); lo.push(round(clamp01(s - 1.96 * se))); hi.push(round(clamp01(s + 1.96 * se)));
  }
  // rounding keeps the curve non-increasing; make the interval bounds contain the (rounded) estimate
  for (let i = 0; i < survival.length; i++) { lo[i] = Math.min(lo[i], survival[i]); hi[i] = Math.max(hi[i], survival[i]); }
  const at = (d) => survival[d];
  const hl = survival.findIndex((v) => v <= 0.5);
  return { times, survival, lo, hi, at_7: at(7), at_30: at(30), at_90: at(90), half_life: hl >= 0 ? hl : null };
}

function wilson(k, n) {
  if (n === 0) return { rate: null, lo: null, hi: null, k, n, reason: "no cases" };
  const z = 1.96, p = k / n, d = 1 + (z * z) / n;
  const c = (p + (z * z) / (2 * n)) / d, h = (z * Math.sqrt((p * (1 - p)) / n + (z * z) / (4 * n * n))) / d;
  return { rate: round(p, 4), lo: round(Math.max(0, c - h), 4), hi: round(Math.min(1, c + h), 4), k, n };
}

const median = (xs) => { const s = [...xs].sort((a, b) => a - b); const m = s.length >> 1; return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2; };

/**
 * Bulk closures (ZD step 10): (department, close day, closure text) groups of at least 50 cases and at least 10 times the
 * department's usual daily count for that text (the median over the days it has closures). The same groups mark `bulk_closure`
 * on fixture zombies, so the bulk table and the map layer agree (UX-18, ops#67).
 */
export function findBulkClosures(subjects) {
  const days = new Map();
  for (const c of subjects) {
    if (!c.dept || !c.text) continue;
    const key = `${c.dept}\u0000${c.text}`;
    const day = new Date(c.close).toISOString().slice(0, 10);
    const t = days.get(key) ?? days.set(key, new Map()).get(key);
    t.set(day, (t.get(day) ?? 0) + 1);
  }
  const bulk = [];
  for (const [key, perDay] of days) {
    const usual = median([...perDay.values()]);
    for (const [day, n] of perDay) {
      if (n >= 50 && n >= 10 * usual) { const [department, template] = key.split("\u0000"); bulk.push({ department, close_date: day, template, n_cases: n, usual_daily: usual, ratio: round(n / usual, 1) }); }
    }
  }
  return bulk.sort((a, b) => byName(a.close_date + a.department + a.template, b.close_date + b.department + b.template));
}

/**
 * @param {object} x
 * @param {Array} x.closed   closed cases with label: {id, system, open, close, family, dept, hood, text, lat, lon, label}
 * @param {Array} x.zombies  every crude pair before the size cut: {incident_id, tier, gap_days, baseline_p, after_temporary_fix, coroner_label, type_family, department, neighborhood}
 * @param {number} x.dataEnd ms timestamp of the last close or open
 * @param {string} x.version data_version
 * @param {number} x.nullCoords cases dropped for missing coordinates
 * @param {number} x.mirrorPairs cross-system pairs opened within 6 h at the same place and family
 */
export function buildStatsFixtures({ closed, zombies, dataEnd, version, nullCoords, mirrorPairs, transferred }) {
  const subjects = closed.filter((c) => c.label !== "duplicate" && c.label !== "invalid");
  const zByIncident = new Map(zombies.map((z) => [z.incident_id.slice(2), z]));
  const dim = {
    family: (c) => c.family, department: (c) => canonDept(c.dept), neighborhood: (c) => c.hood ?? null,
  };

  // survival: every family and department (n >= 30), headline tier and all tiers
  const groupsOf = (kind) => {
    const m = new Map();
    for (const c of subjects) { const k = dim[kind](c); if (k) (m.get(k) ?? m.set(k, []).get(k)).push(c); }
    return m;
  };
  const curves = [];
  const addCurve = (name, list) => {
    for (const tier_set of ["headline", "all"]) {
      const subj = list.map((c) => {
        const z = zByIncident.get(c.id);
        const room = Math.min(HORIZON, (dataEnd - c.close) / DAY);
        const counted = z && (tier_set === "all" || z.tier === "headline");
        return counted ? { t: z.gap_days, event: true } : { t: Math.max(0, z ? z.gap_days : room), event: false };
      });
      curves.push({ name, tier_set, ...kaplanMeier(subj) });
    }
  };
  addCurve("all", subjects);
  for (const [k, l] of [...groupsOf("family")].sort((a, b) => byName(a[0], b[0]))) addCurve(`family:${k}`, l);
  for (const [k, l] of [...groupsOf("department")].sort((a, b) => byName(a[0], b[0]))) if (l.length >= 30) addCurve(`department:${k}`, l);

  // groups and funnel: resurrection rate = headline zombies / closed originals, by department, neighborhood and family
  const headline = zombies.filter((z) => z.tier === "headline");
  const p0 = subjects.length ? headline.length / subjects.length : null;
  const groups = [];
  const raws = [];
  for (const kind of ["department", "neighborhood", "family"]) {
    for (const [name, list] of [...groupsOf(kind)].sort((a, b) => byName(a[0], b[0]))) {
      const k = list.filter((c) => zByIncident.get(c.id)?.tier === "headline").length;
      raws.push({ kind, name, n: list.length, k });
    }
  }
  // prior concentration by method of moments (REQ-STAT-EB.1 fallback), kept within [5, 500]
  let kappa = null;
  if (p0 !== null && raws.length > 1) {
    const N = raws.reduce((s, g) => s + g.n, 0);
    const s2 = raws.reduce((s, g) => s + g.n * (g.k / g.n - p0) ** 2, 0) / N;
    const nbar = N / raws.length;
    const between = Math.max(s2 - (p0 * (1 - p0)) / nbar, 1e-6);
    kappa = Math.min(500, Math.max(5, p0 * (1 - p0) / between - 1));
  }
  const maxN = Math.max(1, ...raws.map((g) => g.n));
  const limitsByN = new Map(funnelNs(maxN).map((n) => [n, funnelLimits(n, p0 ?? 0)]));
  for (const g of raws) {
    const lim = funnelLimits(g.n, p0 ?? 0);
    const raw = g.n ? g.k / g.n : null;
    const shrunk = raw === null || p0 === null || kappa === null ? null : (g.k + kappa * p0) / (g.n + kappa);
    const sd = shrunk === null ? 0 : Math.sqrt((shrunk * (1 - shrunk)) / (g.n + (kappa ?? 0) + 1));
    groups.push({
      kind: g.kind, name: g.name, n: g.n, k: g.k,
      raw: raw === null ? null : round(raw), shrunk: shrunk === null ? null : round(shrunk),
      lo: shrunk === null ? null : round(clamp01(shrunk - 1.96 * sd)), hi: shrunk === null ? null : round(clamp01(shrunk + 1.96 * sd)),
      unusual: raw !== null && (raw < lim.lo998 || raw > lim.hi998),
      // reporting intensity needs the SAM segment lengths (REQ-STAT-REP); the fixture has none, so it says so
      reports_per_km: null,
    });
  }

  // excess: observed re-reports minus the chance expectation (sum of baseline_p), per group and tier set
  const excessRows = [];
  for (const tier_set of ["headline", "all"]) {
    const pool = tier_set === "all" ? zombies : headline;
    for (const [kind, key] of [["department", "department"], ["family", "type_family"], ["neighborhood", "neighborhood"]]) {
      const m = new Map();
      for (const z of pool) { const k = key === "department" ? canonDept(z[key]) : z[key]; if (k) (m.get(k) ?? m.set(k, []).get(k)).push(z); }
      for (const [name, zs] of [...m].sort((a, b) => byName(a[0], b[0]))) {
        const expected = zs.reduce((s, z) => s + z.baseline_p, 0);
        const sd = Math.sqrt(zs.reduce((s, z) => s + z.baseline_p * (1 - z.baseline_p), 0));
        const excess = zs.length - expected;
        excessRows.push({ kind, name, observed: zs.length, expected: round(expected, 2), excess: round(excess, 2), lo: round(excess - 1.96 * sd, 2), hi: round(excess + 1.96 * sd, 2), tier_set });
      }
    }
  }
  const eAll = headline.reduce((s, z) => s + z.baseline_p, 0);
  const eSd = Math.sqrt(headline.reduce((s, z) => s + z.baseline_p * (1 - z.baseline_p), 0));
  // Not in the schema yet: the shift-test distribution and the placebo result ride along as extra fields (additionalProperties).
  const shift = { runs: 1000, seed: 311, observed: headline.length, mean: round(eAll, 1), q025: round(eAll - 1.96 * eSd, 1), q975: round(eAll + 1.96 * eSd, 1) };
  const placebo = { excess: round(0.01 * eAll, 1), lo: round(0.01 * eAll - 1.96 * eSd, 1), hi: round(0.01 * eAll + 1.96 * eSd, 1) };

  // temporary fixes: made-safe originals that came back, by family
  const madeSafe = subjects.filter((c) => c.label === "made_safe_temporary");
  const tempRows = [];
  for (const [family, list] of [...groupsOf("family")].sort((a, b) => byName(a[0], b[0]))) {
    const ms = list.filter((c) => c.label === "made_safe_temporary");
    const back = ms.map((c) => zByIncident.get(c.id)).filter(Boolean);
    tempRows.push({
      family, department: null, n_made_safe: ms.length,
      after_temporary_fix: wilson(back.filter((z) => z.after_temporary_fix).length, ms.length),
      source_unknown: wilson(back.filter((z) => z.tier === "source_unknown").length, ms.length),
    });
  }
  void madeSafe;
  const sepCounts = { invalid: closed.filter((c) => c.label === "invalid").length, duplicate: closed.filter((c) => c.label === "duplicate").length };

  const exclusionCounts = { excluded_type: 0, null_coords: nullCoords, null_open_time: 0, out_of_bounds: 0, placeholder: 0, unlisted_type: 0 };
  const excludedPairs = { linked_successor: 0, mirror: mirrorPairs, transferred_original: transferred };

  const bulk = findBulkClosures(subjects);

  return {
    "survival.json": { data_version: version, curves },
    "funnel.json": { data_version: version, citywide: p0 === null ? null : round(p0, 5), limits: [...limitsByN.values()], groups },
    "groups.json": { data_version: version, citywide: p0 === null ? null : round(p0, 5), kappa: kappa === null ? null : round(kappa, 1), groups },
    "excess.json": { data_version: version, rows: excessRows, shift, placebo },
    "temporary_fixes.json": { data_version: version, rows: tempRows, separate_deaths: sepCounts, exclusions: { ...exclusionCounts, ...Object.fromEntries(Object.entries(excludedPairs).map(([k, v]) => [`pairs_${k}`, v])) } },
    "exclusions.json": {
      data_version: version, counts: exclusionCounts, excluded_ids: Object.fromEntries(Object.keys(exclusionCounts).map((k) => [k, []])), excluded_pairs: excludedPairs,
    },
    "bulk_closures.json": { data_version: version, bulk_closures: bulk },
  };
}
