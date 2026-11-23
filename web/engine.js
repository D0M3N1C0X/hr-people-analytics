// The calculations of the retention check, the same as src/tool_reference.py (tests/js/check_engine.mjs
// recomputes every Python case and fails at the first difference). Runs in the page; nothing is sent anywhere.
//
//   FIELDS                    the columns the tool reads, with the names it recognises them by
//   canonicalRow(raw, comma)  one mapped row of the user's file -> the tool's own record, or an error
//   analyse(rows, periodEnd)  everything the page shows

export const MONTH = 30.4375;
export const SMALL_GROUP = 5;
export const SIGNS = ["below_band", "no_promotion", "fixed_term", "first_year", "onsite"];
const TERMS = [...SIGNS, "top_department"];

export const FIELDS = [
  { key: "id", required: true, aliases: ["employee_id", "employee", "id_dipendente", "matricola", "personnel_number", "emp_id", "worker_id", "numer_pracownika", "personalnummer"] },
  { key: "hire", required: true, aliases: ["hire_date", "start_date", "date_hired", "data_assunzione", "assunzione", "data_zatrudnienia", "eintrittsdatum", "fecha_alta", "fecha_de_alta"] },
  { key: "exit", required: true, aliases: ["exit_date", "termination_date", "leaving_date", "end_date", "data_cessazione", "cessazione", "data_zwolnienia", "austrittsdatum", "fecha_baja", "fecha_de_baja"] },
  { key: "exit_type", aliases: ["exit_reason_type", "termination_type", "leaving_type", "voluntary", "tipo_cessazione", "motivo_cessazione", "tryb_rozwiazania", "austrittsgrund", "tipo_baja"] },
  { key: "department", required: true, aliases: ["dept", "function", "team", "reparto", "funzione", "dzial", "abteilung", "departamento"] },
  { key: "gender", aliases: ["sex", "genere", "sesso", "plec", "geschlecht", "genero", "sexo"] },
  { key: "salary", aliases: ["base_salary", "base_salary_eur", "annual_salary", "salary_eur", "ral", "retribuzione", "stipendio", "wynagrodzenie", "gehalt", "salario"] },
  { key: "band_mid", aliases: ["salary_band_mid", "salary_band_mid_eur", "band_midpoint", "midpoint", "range_mid", "punto_medio_fascia"] },
  { key: "compa", aliases: ["compa_ratio", "comparatio", "compa_ratio_pct"] },
  { key: "msp", aliases: ["months_since_promotion", "mesi_ultima_promozione", "months_since_last_promotion"] },
  { key: "contract", aliases: ["contract_type", "contract", "tipo_contratto", "contratto", "rodzaj_umowy", "vertragsart", "tipo_contrato"] },
  { key: "work_model", aliases: ["work_location_type", "remote", "modalita_lavoro", "tryb_pracy", "arbeitsmodell", "modalidad"] },
];

// ---------------------------------------------------------------- dates as whole days since 1970 (no time zones)
const DAY = 86400000;
export const day = (y, m, d) => Math.round(Date.UTC(y, m - 1, d) / DAY);
const ymd = (n) => { const d = new Date(n * DAY); return [d.getUTCFullYear(), d.getUTCMonth() + 1, d.getUTCDate()]; };
export const iso = (n) => ymd(n).map((v, i) => String(v).padStart(i ? 2 : 4, "0")).join("-");
const monthEnd = (y, m) => day(y, m + 1, 1) - 1;          // Date.UTC rolls month 13 over to January

export function parseDate(v) {
  if (v === null || v === undefined) return null;
  if (typeof v === "number" && isFinite(v)) return v > 20000 && v < 80000 ? Math.round(v) - 25569 : null; // Excel serial
  const s = String(v).trim();
  if (!s) return null;
  let m = s.match(/^(\d{4})-(\d{1,2})-(\d{1,2})/);
  if (m) return valid(+m[1], +m[2], +m[3]);
  m = s.match(/^(\d{1,2})[./-](\d{1,2})[./-](\d{4})$/);           // European order: day first
  if (m) return valid(+m[3], +m[2], +m[1]);
  if (/^\d{5}(\.\d+)?$/.test(s)) return parseDate(Number(s));
  return undefined;                                               // present but unreadable
}
const valid = (y, mo, d) => {
  const n = day(y, mo, d), [yy, mm, dd] = ymd(n);
  return yy === y && mm === mo && dd === d ? n : undefined;
};

export function parseNumber(v, comma) {
  if (v === null || v === undefined || v === "") return null;
  if (typeof v === "number") return isFinite(v) ? v : null;
  let s = String(v).trim().replace(/[\s€$£%]|EUR|PLN|zł/gi, "");
  if (!s) return null;
  s = comma ? s.replace(/\./g, "").replace(",", ".") : s.replace(/,/g, "");
  const n = Number(s);
  return isFinite(n) ? n : undefined;
}

const has = (re) => (v) => re.test(String(v ?? "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase());
const notVoluntary = has(/involunt|non.?volont|niedobrowol|unfreiwill|no.?voluntari|^no$|^0$/);
const saysVoluntary = has(/volunt|resign|dimission|quit|employee.?initiated|rinuncia|wypowiedzenie.?(przez.?)?pracownika|z inicjatywy pracownika|eigenkundigung|kundigung.?arbeitnehmer|baja.?voluntaria|^yes$|^si$|^tak$|^ja$|^1$/);
export const isVoluntary = (v) => !notVoluntary(v) && saysVoluntary(v);
const openEnded = has(/indeterminat|unbefrist|nieokreslon|indefinid|permanent|^cdi/);
export const isFixed = (v) => !openEnded(v) && has(/fixed|temporar|determinat|befrist|okreslon|temporal|^cdd|^ftc/)(v);
export const isOnsite = has(/on.?site|office|presenza|ufficio|in sede|stacjonar|vor ort|buro|presencial/);
export function gender(v) {
  const s = String(v ?? "").normalize("NFD").replace(/[̀-ͯ]/g, "").trim().toLowerCase();
  if (/^(f|female|woman|women|donna|femmina|d|k|kobieta|w|frau|weiblich|mujer|femenino)$/.test(s)) return "F";
  if (/^(m|male|man|men|uomo|maschio|u|mezczyzna|mann|mannlich|hombre|masculino|h)$/.test(s)) return "M";
  return null;
}

// raw: one row with the tool's keys (after the column mapping). Returns { row } or { error: [field, value] }.
export function canonicalRow(raw, comma = false) {
  const id = String(raw.id ?? "").trim();
  if (!id) return { error: ["id", raw.id] };
  const hire = parseDate(raw.hire);
  if (hire == null) return { error: ["hire", raw.hire] };
  const exit = parseDate(raw.exit);
  if (exit === undefined) return { error: ["exit", raw.exit] };
  const dept = String(raw.department ?? "").trim();
  if (!dept) return { error: ["department", raw.department] };
  const row = { id, hire, exit, department: dept,
    voluntary: exit != null && ("exit_type" in raw ? isVoluntary(raw.exit_type) : true) };
  for (const k of ["salary", "band_mid", "compa", "msp"]) {
    if (!(k in raw)) continue;
    const n = parseNumber(raw[k], comma);
    if (n === undefined) return { error: [k, raw[k]] };
    row[k] = n;
  }
  if (row.compa != null && row.compa > 3) row.compa /= 100;                  // written as a percentage
  if (row.compa == null && row.salary != null && row.band_mid) row.compa = row.salary / row.band_mid;
  if (!("compa" in raw) && !("band_mid" in raw)) delete row.compa;
  delete row.band_mid;
  if ("msp" in raw && row.msp != null) row.msp = Math.round(row.msp);
  if ("contract" in raw) row.contract = String(raw.contract ?? "").trim() ? (isFixed(raw.contract) ? "fixed" : "permanent") : null;
  if ("work_model" in raw) row.work_model = String(raw.work_model ?? "").trim() ? (isOnsite(raw.work_model) ? "onsite" : "other") : null;
  if ("gender" in raw) row.gender = gender(raw.gender);
  return { row };
}

// ---------------------------------------------------------------- statistics, as in src/statsx.py
export function erfc(x) {
  // complementary error function to near machine precision: series for small x, continued fraction beyond
  const z = Math.abs(x);
  let r;
  if (z < 2.5) {
    let sum = z, term = z, k = 0;
    while (Math.abs(term) > 1e-17 * Math.abs(sum)) { k++; term *= -z * z / k; sum += term / (2 * k + 1); }
    r = 1 - 2 / Math.sqrt(Math.PI) * sum;
  } else {
    let f = 0;
    for (let k = 60; k >= 1; k--) f = (k / 2) / (z + f);
    r = Math.exp(-z * z) / Math.sqrt(Math.PI) / (z + f);
  }
  return x < 0 ? 2 - r : r;
}
const twoSidedP = (z) => erfc(Math.abs(z) / Math.SQRT2);

function invert(matrix) {
  const n = matrix.length;
  const a = matrix.map((row, i) => [...row, ...row.map((_, j) => (i === j ? 1 : 0))]);
  for (let col = 0; col < n; col++) {
    let pivot = col;
    for (let r = col + 1; r < n; r++) if (Math.abs(a[r][col]) > Math.abs(a[pivot][col])) pivot = r;
    if (Math.abs(a[pivot][col]) < 1e-12) throw new Error("singular");
    [a[col], a[pivot]] = [a[pivot], a[col]];
    const div = a[col][col];
    a[col] = a[col].map((v) => v / div);
    for (let r = 0; r < n; r++) {
      if (r !== col && a[r][col] !== 0) { const f = a[r][col]; a[r] = a[r].map((v, j) => v - f * a[col][j]); }
    }
  }
  return a.map((row) => row.slice(n));
}

export function logit(X, y, maxIter = 50, tol = 1e-8) {
  const n = X.length, k = X[0].length;
  let beta = new Array(k).fill(0), loglik = -Infinity, inv;
  for (let it = 0; it < maxIter; it++) {
    const mu = X.map((row) => { const e = row.reduce((s, v, j) => s + beta[j] * v, 0); return 1 / (1 + Math.exp(-Math.max(-35, Math.min(35, e)))); });
    const hess = Array.from({ length: k }, () => new Array(k).fill(0)), score = new Array(k).fill(0);
    for (let i = 0; i < n; i++) {
      const w = Math.max(mu[i] * (1 - mu[i]), 1e-9);
      for (let a = 0; a < k; a++) { score[a] += X[i][a] * (y[i] - mu[i]); for (let b = a; b < k; b++) hess[a][b] += w * X[i][a] * X[i][b]; }
    }
    for (let a = 0; a < k; a++) for (let b = 0; b < a; b++) hess[a][b] = hess[b][a];
    inv = invert(hess);
    const step = inv.map((row) => row.reduce((s, v, j) => s + v * score[j], 0));
    beta = beta.map((b, j) => b + step[j]);
    let ll = 0;
    for (let i = 0; i < n; i++) ll += y[i] * Math.log(Math.max(mu[i], 1e-12)) + (1 - y[i]) * Math.log(Math.max(1 - mu[i], 1e-12));
    if (Math.abs(ll - loglik) < tol) { loglik = ll; break; }
    loglik = ll;
  }
  const se = inv.map((row, j) => Math.sqrt(row[j]));
  return { coef: beta, se, p: beta.map((b, j) => twoSidedP(se[j] ? b / se[j] : NaN)) };
}

function quantile(xs, q) {
  const s = [...xs].sort((a, b) => a - b);
  if (s.length === 1) return s[0];
  const pos = (s.length - 1) * q, lo = Math.floor(pos), hi = Math.ceil(pos);
  return s[lo] + (s[hi] - s[lo]) * (pos - lo);
}

export function kaplanMeier(subjects) {
  const times = [...new Set(subjects.filter((s) => s[2]).map((s) => s[1]))].sort((a, b) => a - b);
  const out = []; let surv = 1;
  for (const t of times) {
    let atRisk = 0, deaths = 0;
    for (const [a, b, e] of subjects) { if (a < t && t <= b) atRisk++; if (e && b === t) deaths++; }
    if (!atRisk) continue;
    surv *= 1 - deaths / atRisk;
    out.push([t, surv, atRisk]);
  }
  return out;
}
export const survivalAt = (curve, t) => { let s = 1; for (const [time, v] of curve) { if (time > t) break; s = v; } return s; };

// ---------------------------------------------------------------- the analysis
export function window(periodEnd) {
  const [y, m] = ymd(periodEnd), ends = [];
  for (let back = 11; back >= 0; back--) {
    const idx = y * 12 + m - 1 - back;
    ends.push(monthEnd(Math.floor(idx / 12), idx % 12 + 1));
  }
  const [sy, sm] = ymd(ends[0]);
  return { start: day(sy, sm, 1), ends };
}
const months = (a, b) => (b - a) / MONTH;
const wholeMonths = (a, b) => { const [ya, ma] = ymd(a), [yb, mb] = ymd(b); return (yb - ya) * 12 + (mb - ma); };

export function signs(r, at, reference) {
  const out = {};
  if ("compa" in r && r.compa != null) out.below_band = r.compa < 0.92;
  if ("msp" in r && r.msp != null) out.no_promotion = r.msp - wholeMonths(at, reference) > 24;
  if ("contract" in r && r.contract != null) out.fixed_term = r.contract === "fixed";
  out.first_year = wholeMonths(r.hire, at) < 12;
  if ("work_model" in r && r.work_model != null) out.onsite = r.work_model === "onsite";
  return out;
}

export function analyse(rows, periodEnd) {
  const { start, ends } = window(periodEnd), end = ends[ends.length - 1];
  const inWindow = (r) => r.exit != null && start <= r.exit && r.exit <= end;
  const activeOn = (r, d) => r.hire <= d && (r.exit == null || r.exit > d);
  const turnover = (g) => {
    let sum = 0; for (const d of ends) for (const r of g) if (activeOn(r, d)) sum++;
    return [sum / 12, g.filter((r) => inWindow(r) && r.voluntary).length, g.filter(inWindow).length];
  };
  const [avg, vol, all] = turnover(rows);
  const out = { start: iso(start), end: iso(end), employees: rows.length, active_end: rows.filter((r) => activeOn(r, end)).length,
    avg_headcount: avg, voluntary: vol, exits: all, voluntary_rate: avg ? vol / avg : null, exit_rate: avg ? all / avg : null };

  const depts = [...new Set(rows.map((r) => r.department))].sort(cmp);
  const by = depts.map((d) => { const [a, v] = turnover(rows.filter((r) => r.department === d)); return { department: d, avg_headcount: a, voluntary: v, rate: a ? v / a : null }; });
  by.sort((p, q) => ((q.rate || 0) - (p.rate || 0)) || cmp(p.department, q.department));
  out.departments = by;

  const subjects = [];
  for (const r of rows) {
    if (r.exit != null && r.exit < start) continue;
    const entry = Math.max(0, months(r.hire, start)), t = months(r.hire, inWindow(r) ? r.exit : end);
    if (t > entry) subjects.push([[entry, t, inWindow(r) && r.voluntary ? 1 : 0], r]);
  }
  const surv = (g) => { const c = kaplanMeier(g.map(([s]) => s)); return c.length ? Object.fromEntries([12, 24, 36].map((t) => [String(t), survivalAt(c, t)])) : null; };
  out.survival = surv(subjects);
  if (subjects.some(([, r]) => r.compa != null)) {
    out.survival_below = surv(subjects.filter(([, r]) => r.compa != null && r.compa < 0.92));
    out.survival_at = surv(subjects.filter(([, r]) => r.compa != null && r.compa >= 0.92));
  }

  const top = by.length && by[0].rate ? by[0].department : null;
  const frame = rows.filter((r) => r.hire < start && (r.exit == null || r.exit >= start));
  const feats = frame.map((r) => ({ ...signs(r, start, inWindow(r) ? r.exit : end), ...(top ? { top_department: r.department === top } : {}) }));
  const y = frame.map((r) => (inWindow(r) && r.voluntary ? 1 : 0));
  const events = y.reduce((s, v) => s + v, 0);
  const names = TERMS.filter((k) => feats.length && feats.every((f) => k in f) && (() => {
    const share = feats.reduce((s, f) => s + (f[k] ? 1 : 0), 0) / feats.length; return share >= 0.01 && share <= 0.99; })());
  out.drivers = null;
  if (names.length && frame.length >= 50 && events >= 10 && events < y.length) {
    try {
      const fit = logit(feats.map((f) => [1, ...names.map((k) => (f[k] ? 1 : 0))]), y);
      out.drivers = { n: frame.length, events, top_department: top,
        terms: names.map((k, j) => ({ term: k, odds_ratio: Math.exp(fit.coef[j + 1]), p: fit.p[j + 1] })) };
    } catch { out.drivers = null; }
  }

  out.team = depts.map((d) => {
    const members = rows.filter((r) => r.department === d && activeOn(r, end));
    if (members.length < SMALL_GROUP) return { department: d, active: members.length, two_or_more: null };
    const flagged = members.filter((r) => Object.values(signs(r, end, end)).filter(Boolean).length >= 2).length;
    return { department: d, active: members.length, two_or_more: flagged };
  });

  const pay = rows.filter((r) => activeOn(r, end) && r.salary != null && (r.gender === "F" || r.gender === "M"));
  const women = pay.filter((r) => r.gender === "F").map((r) => r.salary), men = pay.filter((r) => r.gender === "M").map((r) => r.salary);
  out.pay = null;
  if (women.length >= SMALL_GROUP && men.length >= SMALL_GROUP) {
    const ordered = [...pay].sort((a, b) => a.salary - b.salary || cmp(a.id, b.id));
    const q = (i) => Math.floor(4 * i / ordered.length);
    const share = (k) => { let w = 0, n = 0; ordered.forEach((r, i) => { if (q(i) === k) { n++; if (r.gender === "F") w++; } }); return w / n; };
    const mean = (xs) => xs.reduce((s, v) => s + v, 0) / xs.length;
    const mm = mean(men), mf = mean(women), medM = quantile(men, 0.5), medF = quantile(women, 0.5);
    out.pay = { women: women.length, men: men.length, mean_gap: (mm - mf) / mm, median_gap: (medM - medF) / medM,
      women_bottom: share(0), women_top: share(3) };
  }
  return out;
}

function cmp(a, b) { return a < b ? -1 : a > b ? 1 : 0; }     // code-point order, as Python sorts strings
