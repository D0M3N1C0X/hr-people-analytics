// Recomputes with web/engine.js every case src/tool_reference.py computed, and fails at the first difference.
// The repository case goes through the tool's own column matching and parsing, from data/employees.csv.
import { readFileSync } from "node:fs";
import { analyse, canonicalRow, FIELDS, parseDate, parseNumber, isVoluntary, isFixed, isOnsite, gender, erfc, day } from "../../web/engine.js";
import { parseCsv, matchColumns, applyMapping } from "../../web/design/table.js";

const root = new URL("../../", import.meta.url);
const V = JSON.parse(readFileSync(new URL("tests/fixtures/tool_vectors.json", root)));
let checks = 0, failures = 0;
const fail = (what) => { failures++; if (failures <= 25) console.error("difference:", what); };

function compare(a, b, path) {
  if (b === null || typeof b !== "object") {
    checks++;
    if (typeof b === "number" && typeof a === "number") {
      const tol = /odds_ratio|\.p$/.test(path) ? 1e-6 : 1e-9;
      if (Math.abs(a - b) > tol * Math.max(1, Math.abs(b))) fail(`${path}: ${a} vs ${b}`);
    } else if (a !== b) fail(`${path}: ${JSON.stringify(a)} vs ${JSON.stringify(b)}`);
    return;
  }
  if (a === null || typeof a !== "object") { checks++; fail(`${path}: ${JSON.stringify(a)} vs object`); return; }
  const keys = new Set([...Object.keys(a), ...Object.keys(b)]);
  for (const k of keys) compare(a[k], b[k], `${path}.${k}`);
}

const toDay = (s) => (s ? parseDate(s) : null);
for (const c of V.cases) {
  let rows;
  if (c.source) {
    const { headers, rows: raw, decimalComma } = parseCsv(readFileSync(new URL(c.source, root), "utf8"));
    const { mapping, missing } = matchColumns(headers, FIELDS);
    if (missing.length) { fail(`${c.name}: columns not matched ${missing}`); continue; }
    rows = applyMapping(raw, mapping).map((r) => canonicalRow(r, decimalComma)).map((x) => {
      if (x.error) fail(`${c.name}: unreadable ${x.error}`); return x.row; });
  } else {
    rows = c.rows.values.map((vals) => {
      const r = Object.fromEntries(c.rows.fields.map((f, i) => [f, vals[i]]));
      r.hire = toDay(r.hire); r.exit = toDay(r.exit);
      for (const k of Object.keys(r)) if (r[k] === null && !["exit"].includes(k)) r[k] = null;
      return r;
    });
  }
  compare(analyse(rows, toDay(c.period_end)), c.result, c.name);
}

// Reading values the way real exports write them
const same = (got, want, what) => { checks++; if (JSON.stringify(got) !== JSON.stringify(want)) fail(`${what}: ${JSON.stringify(got)}`); };
same(parseDate("2026-03-01"), day(2026, 3, 1), "iso date");
same(parseDate("01/03/2026"), day(2026, 3, 1), "day first");
same(parseDate("1.3.2026"), day(2026, 3, 1), "dotted");
same(parseDate(46082), day(2026, 3, 1), "Excel serial");
same(parseDate("31/02/2026"), undefined, "impossible date");
same(parseDate(""), null, "empty date");
same(parseNumber("1.539,70", true), 1539.7, "decimal comma");
same(parseNumber("€ 1,539.70", false), 1539.7, "currency");
same(parseNumber("abc", false), undefined, "not a number");
for (const v of ["Voluntary", "Dimissioni volontarie", "resignation", "Wypowiedzenie przez pracownika", "Eigenkündigung", "baja voluntaria"]) same(isVoluntary(v), true, `voluntary ${v}`);
for (const v of ["Involuntary", "Licenziamento", "End of contract", "Dismissal", ""]) same(isVoluntary(v), false, `not voluntary ${v}`);
for (const [v, w] of [["Fixed-term", true], ["Tempo determinato", true], ["befristet", true], ["na czas określony", true], ["Permanent", false], ["indeterminato", false], ["unbefristet", false], ["na czas nieokreślony", false]]) same(isFixed(v), w, `fixed ${v}`);
for (const [v, w] of [["Onsite", true], ["In ufficio", true], ["Hybrid", false], ["Remote", false]]) same(isOnsite(v), w, `onsite ${v}`);
for (const [v, w] of [["F", "F"], ["Donna", "F"], ["kobieta", "F"], ["M", "M"], ["Uomo", "M"], ["X", null], ["", null]]) same(gender(v), w, `gender ${v}`);
same(canonicalRow({ id: "1", hire: "2024-01-01", exit: "", department: "HR", compa: "95%" }).row.compa, 0.95, "compa as percent");
same(canonicalRow({ id: "1", hire: "2024-01-01", exit: "", department: "HR", salary: "30000", band_mid: "40000" }).row.compa, 0.75, "compa from band");
same(canonicalRow({ id: "1", hire: "yesterday", exit: "", department: "HR" }).error, ["hire", "yesterday"], "bad hire date");
for (const [x, want] of [[0, 1], [0.5, 0.4795001221869535], [1.96, 0.005573724535172132], [3, 2.2090496998585438e-05], [6, 2.1519736712498916e-17]]) {   // math.erfc in Python
  checks++; if (Math.abs(erfc(x) - want) > 1e-12 * Math.max(1, want) && Math.abs(erfc(x) / want - 1) > 1e-9) fail(`erfc(${x}) = ${erfc(x)}`);
}
console.log(`${checks - failures} of ${checks} values agree with Python in ${V.cases.length} cases`);
process.exit(failures ? 1 : 0);
