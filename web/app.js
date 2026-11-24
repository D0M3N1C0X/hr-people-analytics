// The retention check page: read the file, match its columns, run web/engine.js, show and export the results.
import { createI18n } from "./design/i18n.js";
import { readTable, matchColumns, applyMapping, savedMapping, rememberMapping, download } from "./design/table.js";
import { writeXlsx } from "./design/xlsx.js";
import { FIELDS, canonicalRow, analyse, parseDate, day, iso, SMALL_GROUP } from "./engine.js";

const T = {
  en: {
    brand: "People analytics", eyebrow: "Retention check · from your own HRIS export",
    title: "Why are people leaving, and how long do they stay?",
    lead: "Load one row per employee, leavers included. You get turnover by department, how many hires are still there after one, two and three years, what goes with resigning, warning signs team by team, and the pay gap.",
    privacy: "Your file stays on this computer: it is read by this page and sent nowhere. Go offline after the page has loaded and it still works.",
    step1: "Your employee file",
    step1sub: "An Excel or CSV export: employee number, hire date, leaving date (empty for people still employed) and department are enough. Pay, contract and promotion columns add the rest.",
    drop: "Choose the file, or drop it here", dropHint: ".xlsx or .csv", sample: "Try it on the example: 4,000 employees",
    template: "Column template", step2: "Check the columns",
    step2sub: "The page matched your columns by name. Correct any it got wrong; the starred ones are needed.",
    periodLabel: "Last month of the twelve analysed", run: "Show the results", none: "— not in the file —",
    f_id: "Employee number", f_hire: "Hire date", f_exit: "Leaving date", f_exit_type: "Type of leaving",
    f_department: "Department", f_gender: "Sex", f_salary: "Annual base pay", f_band_mid: "Mid-point of the pay band",
    f_compa: "Compa-ratio", f_msp: "Months since last promotion", f_contract: "Contract type", f_work_model: "Work model",
    h_exit: "empty for people still employed", h_exit_type: "voluntary or not; without it every exit counts as a resignation",
    h_compa: "or the pay band mid-point, from which it is computed", h_msp: "as of the leaving date or the end of the file",
    errMissing: "These columns are needed: {cols}.", errRead: "The file could not be read: {msg}",
    errRows: "{n} rows could not be read and were left out, for example row {row}: {field} “{value}”.",
    errNone: "No row could be read. Check that the dates are written as 2026-03-31 or 31/03/2026.",
    noType: "There is no type-of-leaving column, so every exit is counted as a resignation.",
    kAvg: "Average headcount", kVol: "Voluntary turnover", kAll: "All exits", kYear: "Still here after a year",
    depSub: "Exits from {start} to {end} as a share of the average of twelve month-end headcounts.",
    dDept: "Department", dAvg: "Average headcount", dVol: "Resigned", dRate: "Voluntary turnover",
    sTenure: "After", sAll: "Everyone", sAt: "Paid at or above 0.92 of band", sBelow: "Paid below", year1: "1 year", years: "{n} years",
    drvSub: "People employed on {start}, the signs they carried that day, and who resigned in the next twelve months: {n} people, {e} resignations.",
    drvNone: "Not enough to estimate: it needs at least 50 people employed when the period began, 10 resignations among them, and at least one sign column.",
    drvSign: "Sign", drvOr: "Odds ratio", drvP: "p-value", drvShare: "Reading",
    below_band: "Paid below 0.92 of band", no_promotion: "No promotion in 24+ months", fixed_term: "Fixed-term contract",
    first_year: "First year of tenure", onsite: "Fully onsite", top_department: "Works in {d}",
    clear: "clear", weak: "weak evidence", none_: "no evidence",
    tDept: "Department", tActive: "Employed now", tTwo: "With two or more signs", tShare: "Share", small: "fewer than {n}: not shown",
    rulesTitle: "Use it for conversations, never for decisions about people",
    rule1: "A team with many signs is a reason for a manager and HR to talk with that team.",
    rule2: "Not for pay, counter-offers, promotion, training, ratings or dismissal: a decision taken on a predicted intention to leave is unequal treatment waiting to happen.",
    rule3: "A scoring model built on this goes further, and is high-risk under the AI Act: see the <a href=\"https://github.com/D0M3N1C0X/hr-people-analytics/blob/main/docs/model_card.md\">model card</a>.",
    depTitle: "Turnover by department", survTitle: "How long people stay",
    survSub: "Of a hundred people hired, how many are still here after one, two and three years. People hired before the period count from the tenure they had when it began, so early leavers the file never saw are not credited as stayers.",
    drvTitle: "What goes with resigning",
    drvNote: "An odds ratio of 2 means twice the odds of resigning for people with that sign, other signs held equal. It shows where to look, not what caused it.",
    teamTitle: "Warning signs, team by team",
    teamSub: "People employed at the end of the period who carry two or more of the warning signs above. Counts per department only: this page never lists names, and teams under five people are not shown.",
    payTitle: "The gender pay gap",
    paySub: "Base pay of people employed at the end of the period, men as the reference, as Directive (EU) 2023/970 measures it.",
    payNote: "Base pay only. A Directive report also counts bonuses, allowances and benefits, and the gap by category of workers: the pay transparency kit does that part.",
    payNone: "Needs a sex column and a pay column, with at least five women and five men employed.",
    pMean: "Mean gap", pMedian: "Median gap", pBottom: "Women in the lowest pay quarter", pTop: "Women in the highest pay quarter",
    download: "Download the results (Excel)", print: "Print",
    foot: "The calculations are the same as the <a href=\"https://github.com/D0M3N1C0X/hr-people-analytics\">report's</a>, checked against its Python on every change. Built by Domenico Perroni.",
    xSummary: "Summary", xDepartments: "Departments", xSurvival: "Survival", xDrivers: "Drivers", xTeams: "Teams", xPay: "Pay gap",
    xMeasure: "Measure", xValue: "Value", fileOut: "retention-check",
  },
  it: {
    brand: "People analytics", eyebrow: "Analisi della retention · dall'export del tuo gestionale HR",
    title: "Perché le persone se ne vanno, e quanto restano?",
    lead: "Carica una riga per dipendente, cessati compresi. Ottieni il turnover per reparto, quanti assunti restano dopo uno, due e tre anni, cosa si accompagna alle dimissioni, i segnali di rischio reparto per reparto e il gap retributivo.",
    privacy: "Il file resta su questo computer: lo legge questa pagina e non va da nessuna parte. Scollegati dalla rete dopo aver aperto la pagina: funziona lo stesso.",
    step1: "Il file dei dipendenti",
    step1sub: "Un export Excel o CSV: matricola, data di assunzione, data di cessazione (vuota per chi è in forza) e reparto bastano. Retribuzione, contratto e promozioni aggiungono il resto.",
    drop: "Scegli il file, o trascinalo qui", dropHint: ".xlsx o .csv", sample: "Prova con l'esempio: 4.000 dipendenti",
    template: "Modello delle colonne", step2: "Controlla le colonne",
    step2sub: "La pagina ha abbinato le colonne per nome. Correggi quelle sbagliate; quelle con l'asterisco servono.",
    periodLabel: "Ultimo mese dei dodici analizzati", run: "Mostra i risultati", none: "— non presente —",
    f_id: "Matricola", f_hire: "Data di assunzione", f_exit: "Data di cessazione", f_exit_type: "Tipo di cessazione",
    f_department: "Reparto", f_gender: "Sesso", f_salary: "Retribuzione annua base", f_band_mid: "Punto medio della fascia",
    f_compa: "Compa-ratio", f_msp: "Mesi dall'ultima promozione", f_contract: "Tipo di contratto", f_work_model: "Modalità di lavoro",
    h_exit: "vuota per chi è in forza", h_exit_type: "volontaria o no; senza, ogni cessazione conta come dimissione",
    h_compa: "o il punto medio della fascia, da cui si calcola", h_msp: "alla data di cessazione o alla fine del file",
    errMissing: "Servono queste colonne: {cols}.", errRead: "Il file non si legge: {msg}",
    errRows: "{n} righe non si leggono e sono state escluse, per esempio la riga {row}: {field} «{value}».",
    errNone: "Nessuna riga leggibile. Controlla che le date siano scritte come 2026-03-31 o 31/03/2026.",
    noType: "Manca la colonna del tipo di cessazione: ogni cessazione è contata come dimissione.",
    kAvg: "Organico medio", kVol: "Turnover volontario", kAll: "Tutte le cessazioni", kYear: "Ancora qui dopo un anno",
    depSub: "Cessazioni dal {start} al {end} sull'organico medio di dodici fine mese.",
    dDept: "Reparto", dAvg: "Organico medio", dVol: "Dimissioni", dRate: "Turnover volontario",
    sTenure: "Dopo", sAll: "Tutti", sAt: "Pagati da 0,92 della fascia in su", sBelow: "Pagati sotto", year1: "1 anno", years: "{n} anni",
    drvSub: "Chi era in forza il {start}, i segnali che aveva quel giorno e chi si è dimesso nei dodici mesi seguenti: {n} persone, {e} dimissioni.",
    drvNone: "Non basta per stimarlo: servono almeno 50 persone in forza all'inizio del periodo, 10 dimissioni tra loro e almeno una colonna di segnali.",
    drvSign: "Segnale", drvOr: "Odds ratio", drvP: "p-value", drvShare: "Lettura",
    below_band: "Pagato sotto 0,92 della fascia", no_promotion: "Nessuna promozione da 24+ mesi", fixed_term: "Contratto a termine",
    first_year: "Primo anno di anzianità", onsite: "Interamente in sede", top_department: "Lavora in {d}",
    clear: "netta", weak: "debole", none_: "nessuna evidenza",
    tDept: "Reparto", tActive: "In forza", tTwo: "Con due o più segnali", tShare: "Quota", small: "meno di {n}: non mostrato",
    rulesTitle: "Serve per parlare con le persone, mai per decidere su di loro",
    rule1: "Un reparto con molti segnali è un motivo perché il responsabile e l'HR parlino con quel reparto.",
    rule2: "Non per retribuzione, controproposte, promozioni, formazione, valutazioni o licenziamenti: una decisione presa su una presunta intenzione di andarsene è una disparità di trattamento.",
    rule3: "Un modello che dà un punteggio alle persone va oltre, ed è ad alto rischio per l'AI Act: vedi la <a href=\"https://github.com/D0M3N1C0X/hr-people-analytics/blob/main/docs/model_card.md\">scheda del modello</a> (in inglese).",
    depTitle: "Turnover per reparto", survTitle: "Quanto restano le persone",
    survSub: "Su cento assunti, quanti sono ancora qui dopo uno, due e tre anni. Chi è stato assunto prima del periodo conta dall'anzianità che aveva quando è iniziato, così chi se n'è andato prima e il file non vede non passa per uno che è rimasto.",
    drvTitle: "Cosa si accompagna alle dimissioni",
    drvNote: "Un odds ratio di 2 vuol dire il doppio delle probabilità relative di dimettersi per chi ha quel segnale, a parità degli altri. Dice dove guardare, non la causa.",
    teamTitle: "Segnali di rischio, reparto per reparto",
    teamSub: "Persone in forza a fine periodo con due o più dei segnali qui sopra. Solo conteggi per reparto: la pagina non elenca mai nomi, e i reparti con meno di cinque persone non sono mostrati.",
    payTitle: "Il gap retributivo di genere",
    paySub: "Retribuzione base di chi è in forza a fine periodo, uomini come riferimento, come la misura la Direttiva (UE) 2023/970.",
    payNote: "Solo retribuzione base. Il report della Direttiva conta anche bonus, indennità e benefit, e il gap per categoria di lavoratori: lo fa il kit sulla trasparenza retributiva.",
    payNone: "Servono una colonna del sesso e una della retribuzione, con almeno cinque donne e cinque uomini in forza.",
    pMean: "Gap medio", pMedian: "Gap mediano", pBottom: "Donne nel quarto più basso", pTop: "Donne nel quarto più alto",
    download: "Scarica i risultati (Excel)", print: "Stampa",
    foot: "I calcoli sono gli stessi del <a href=\"https://github.com/D0M3N1C0X/hr-people-analytics\">rapporto</a>, verificati contro il suo Python a ogni modifica. Realizzato da Domenico Perroni.",
    xSummary: "Sintesi", xDepartments: "Reparti", xSurvival: "Permanenza", xDrivers: "Fattori", xTeams: "Reparti a rischio", xPay: "Gap retributivo",
    xMeasure: "Misura", xValue: "Valore", fileOut: "analisi-retention",
  },
};

const i18n = createI18n(T, "en");
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
let table = null, mapping = {}, result = null, rows = [];

function message(id, text) { const el = $(id); el.textContent = text || ""; el.classList.toggle("is-shown", !!text); }

async function load(file) {
  message("errore", "");
  try {
    table = await readTable(file);
  } catch (err) { message("errore", i18n.t("errRead", { msg: err.message })); return; }
  $("file-name").textContent = file.name;
  $("drop").classList.add("is-done");
  mapping = matchColumns(table.headers, FIELDS, savedMapping("retention", table.headers)).mapping;
  drawMapping();
  $("colonne").style.display = "block";
  $("risultati").style.display = "none";
  // the period ends with the latest month the file has a date in
  let latest = 0;
  for (const r of table.rows) for (const k of ["hire", "exit"]) {
    const d = mapping[k] ? parseDate(r[mapping[k]]) : null;
    if (d && d > latest) latest = d;
  }
  if (latest) $("periodo").value = iso(latest).slice(0, 7);
  $("colonne").scrollIntoView({ behavior: "smooth", block: "start" });
}

function drawMapping() {
  const opts = (sel) => `<option value="">${esc(i18n.t("none"))}</option>` +
    table.headers.map((h) => `<option${h === sel ? " selected" : ""}>${esc(h)}</option>`).join("");
  $("mappa").innerHTML = FIELDS.map((f) => {
    const hint = T[i18n.lang][`h_${f.key}`];
    return `<div class="s-map-row${f.required && !mapping[f.key] ? " is-missing" : ""}">
      <label class="need" for="m-${f.key}">${esc(i18n.t(`f_${f.key}`))}${f.required ? " *" : ""}${hint ? `<small>${esc(hint)}</small>` : ""}</label>
      <select class="s-select" id="m-${f.key}" data-key="${f.key}">${opts(mapping[f.key])}</select></div>`;
  }).join("");
  $("mappa").querySelectorAll("select").forEach((s) => s.addEventListener("change", () => {
    mapping[s.dataset.key] = s.value || undefined;
    drawMapping();
  }));
}

function run() {
  message("errore", ""); message("avviso", "");
  const missing = FIELDS.filter((f) => f.required && !mapping[f.key]).map((f) => i18n.t(`f_${f.key}`));
  if (missing.length) { message("avviso", i18n.t("errMissing", { cols: missing.join(", ") })); return; }
  rememberMapping("retention", table.headers, mapping);
  const used = Object.fromEntries(Object.entries(mapping).filter(([, h]) => h));
  rows = []; const bad = [];
  applyMapping(table.rows, used).forEach((raw, i) => {
    const x = canonicalRow(raw, table.decimalComma);
    if (x.row) rows.push(x.row); else bad.push([i + 2, ...x.error]);
  });
  const notes = [];
  if (!used.exit_type) notes.push(i18n.t("noType"));
  if (bad.length) notes.push(i18n.t("errRows", { n: bad.length, row: bad[0][0], field: i18n.t(`f_${bad[0][1]}`), value: bad[0][2] ?? "" }));
  if (!rows.length) { message("avviso", i18n.t("errNone")); return; }
  message("avviso", notes.join(" "));
  const [y, m] = ($("periodo").value || "").split("-").map(Number);
  const periodEnd = y && m ? day(y, m + 1, 1) - 1 : Math.max(...rows.map((r) => Math.max(r.hire, r.exit ?? 0)));
  result = analyse(rows, periodEnd);
  draw();
  $("risultati").style.display = "block";
  $("risultati").scrollIntoView({ behavior: "smooth", block: "start" });
}

const pct = (x, d = 1) => (x == null ? "–" : i18n.percent(x, d));
const date = (s) => new Intl.DateTimeFormat(i18n.lang === "it" ? "it-IT" : "en-GB", { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" })
  .format(new Date(`${s}T00:00:00Z`));
const signName = (k) => i18n.t(k, { d: result.drivers?.top_department ?? "" });
const reading = (p) => (p < 0.01 ? i18n.t("clear") : p < 0.1 ? i18n.t("weak") : i18n.t("none_"));

function draw() {
  const r = result;
  $("kpis").innerHTML = [[i18n.t("kAvg"), i18n.number(r.avg_headcount)], [i18n.t("kVol"), pct(r.voluntary_rate)],
    [i18n.t("kAll"), pct(r.exit_rate)], [i18n.t("kYear"), pct(r.survival?.["12"], 0)]]
    .map(([k, v]) => `<div class="s-kpi"><div class="k">${esc(k)}</div><div class="v">${esc(v)}</div></div>`).join("");

  $("dep-sub").textContent = i18n.t("depSub", { start: date(r.start), end: date(r.end) });
  const maxRate = Math.max(...r.departments.map((d) => d.rate || 0), 0.0001);
  $("tab-dep").innerHTML = `<thead><tr><th>${i18n.t("dDept")}</th><th class="num">${i18n.t("dAvg")}</th><th class="num">${i18n.t("dVol")}</th><th class="num">${i18n.t("dRate")}</th><th></th></tr></thead><tbody>` +
    r.departments.map((d, i) => `<tr><td>${esc(d.department)}</td><td class="num">${i18n.number(d.avg_headcount)}</td><td class="num">${d.voluntary}</td>
      <td class="num">${pct(d.rate)}</td><td style="width:30%"><span class="bar${i === 0 && d.rate ? " is-top" : ""}" style="width:${Math.round(100 * (d.rate || 0) / maxRate)}%"></span></td></tr>`).join("") + "</tbody>";

  const cols = [["sAll", r.survival]];
  if (r.survival_at) cols.push(["sAt", r.survival_at], ["sBelow", r.survival_below]);
  $("tab-surv").innerHTML = `<thead><tr><th>${i18n.t("sTenure")}</th>${cols.map(([k]) => `<th class="num">${i18n.t(k)}</th>`).join("")}</tr></thead><tbody>` +
    ["12", "24", "36"].map((t) => `<tr><td>${t === "12" ? i18n.t("year1") : i18n.t("years", { n: Number(t) / 12 })}</td>${cols.map(([, s]) => `<td class="num">${pct(s?.[t], 0)}</td>`).join("")}</tr>`).join("") + "</tbody>";

  if (r.drivers) {
    $("drv-sub").textContent = i18n.t("drvSub", { start: date(r.start), n: i18n.number(r.drivers.n), e: r.drivers.events });
    $("tab-drv").innerHTML = `<thead><tr><th>${i18n.t("drvSign")}</th><th class="num">${i18n.t("drvOr")}</th><th class="num">${i18n.t("drvP")}</th><th>${i18n.t("drvShare")}</th></tr></thead><tbody>` +
      [...r.drivers.terms].sort((a, b) => b.odds_ratio - a.odds_ratio).map((t) => `<tr><td>${esc(signName(t.term))}</td>
        <td class="num">${i18n.number(t.odds_ratio, 2)}</td><td class="num">${t.p < 0.001 ? "<0.001" : i18n.number(t.p, 3)}</td>
        <td><span class="s-pill ${t.p < 0.01 ? "is-high" : t.p < 0.1 ? "is-medium" : "is-ok"}">${esc(reading(t.p))}</span></td></tr>`).join("") + "</tbody>";
  } else { $("drv-sub").textContent = i18n.t("drvNone"); $("tab-drv").innerHTML = ""; }

  $("tab-team").innerHTML = `<thead><tr><th>${i18n.t("tDept")}</th><th class="num">${i18n.t("tActive")}</th><th class="num">${i18n.t("tTwo")}</th><th class="num">${i18n.t("tShare")}</th></tr></thead><tbody>` +
    r.team.map((t) => t.two_or_more == null
      ? `<tr><td>${esc(t.department)}</td><td class="num" colspan="3">${esc(i18n.t("small", { n: SMALL_GROUP }))}</td></tr>`
      : `<tr><td>${esc(t.department)}</td><td class="num">${t.active}</td><td class="num">${t.two_or_more}</td><td class="num">${pct(t.two_or_more / t.active, 0)}</td></tr>`).join("") + "</tbody>";

  $("kpis-pay").innerHTML = r.pay
    ? [[i18n.t("pMean"), pct(r.pay.mean_gap)], [i18n.t("pMedian"), pct(r.pay.median_gap)], [i18n.t("pBottom"), pct(r.pay.women_bottom, 0)], [i18n.t("pTop"), pct(r.pay.women_top, 0)]]
      .map(([k, v]) => `<div class="s-kpi"><div class="k">${esc(k)}</div><div class="v">${esc(v)}</div></div>`).join("")
    : `<p class="s-sub">${esc(i18n.t("payNone"))}</p>`;
}

function exportXlsx() {
  const r = result, t = i18n.t;
  const sheets = [
    { name: t("xSummary"), widths: [42, 16], rows: [[t("xMeasure"), t("xValue")], ["Start", r.start], ["End", r.end],
      [t("kAvg"), r.avg_headcount], [t("dVol"), r.voluntary], [t("kVol"), r.voluntary_rate], [t("kAll"), r.exit_rate]] },
    { name: t("xDepartments"), widths: [28, 16, 12, 18], rows: [[t("dDept"), t("dAvg"), t("dVol"), t("dRate")],
      ...r.departments.map((d) => [d.department, d.avg_headcount, d.voluntary, d.rate])] },
    { name: t("xSurvival"), widths: [16, 14, 26, 14], rows: [[t("sTenure"), t("sAll"), t("sAt"), t("sBelow")],
      ...["12", "24", "36"].map((k) => [`${k} m`, r.survival?.[k] ?? null, r.survival_at?.[k] ?? null, r.survival_below?.[k] ?? null])] },
    { name: t("xTeams"), widths: [28, 14, 22], rows: [[t("tDept"), t("tActive"), t("tTwo")],
      ...r.team.map((x) => [x.department, x.active, x.two_or_more ?? t("small", { n: SMALL_GROUP })])] },
  ];
  if (r.drivers) sheets.splice(3, 0, { name: t("xDrivers"), widths: [34, 12, 12], rows: [[t("drvSign"), t("drvOr"), t("drvP")],
    ...r.drivers.terms.map((x) => [signName(x.term), x.odds_ratio, x.p])] });
  if (r.pay) sheets.push({ name: t("xPay"), widths: [36, 12], rows: [[t("xMeasure"), t("xValue")], [t("pMean"), r.pay.mean_gap],
    [t("pMedian"), r.pay.median_gap], [t("pBottom"), r.pay.women_bottom], [t("pTop"), r.pay.women_top]] });
  download(writeXlsx(sheets), `${t("fileOut")}-${r.end}.xlsx`, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet");
}

$("file").addEventListener("change", (e) => e.target.files[0] && load(e.target.files[0]));
const drop = $("drop");
drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("is-over"); });
drop.addEventListener("dragleave", () => drop.classList.remove("is-over"));
drop.addEventListener("drop", (e) => { e.preventDefault(); drop.classList.remove("is-over"); if (e.dataTransfer.files[0]) load(e.dataTransfer.files[0]); });
$("esempio").addEventListener("click", async () => {
  const res = await fetch("sample_employees.csv");
  if (!res.ok) { message("errore", i18n.t("errRead", { msg: res.status })); return; }
  load(new File([await res.text()], "sample_employees.csv", { type: "text/csv" }));
});
$("calcola").addEventListener("click", run);
$("scarica").addEventListener("click", exportXlsx);
$("stampa").addEventListener("click", () => window.print());
i18n.apply();
i18n.onChange(() => { if (table) drawMapping(); if (result) draw(); });
