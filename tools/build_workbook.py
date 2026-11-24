"""
deliverables/people_analytics.xlsx - the report's core figures as live formulas, reconciled with Python.

The pipeline itself stays standard-library only. This builder is the one place that uses packages
(openpyxl to write the file, excel-twin to keep it byte-stable and to check it), and it is run on its own:

    pip install -r tools/requirements.txt
    python3 tools/build_workbook.py                                   # writes the workbook
    excel-twin recalc deliverables/people_analytics.xlsx build/       # LibreOffice calculates it
    excel-twin check build/people_analytics.xlsx                       # every figure matches Python

Each sheet answers one question from the report with formulas over the Data sheet, so anyone can audit a
number by clicking on it: turnover by department from twelve month-end headcounts, the warning signs the
attrition model is built on, the Article 9 pay-gap items and the Article 10 categories. The Reconciliation
sheet sets each formula against the value Python computed.
"""

from __future__ import annotations

import sys
from collections import Counter
from datetime import date
from pathlib import Path

from openpyxl import Workbook
from openpyxl.formatting.rule import CellIsRule
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.formula import ArrayFormula

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import analysis_attrition as att  # noqa: E402
import analysis_pay_gap as pg  # noqa: E402
from hrlib import FEATURE_END, SNAPSHOT, WINDOW_START, load_cases, load_employees, monthly_headcount  # noqa: E402
from statsx import median, quantile  # noqa: E402

OUT = ROOT / "deliverables" / "people_analytics.xlsx"
BLUE, GREEN, INK, MUTED = "0B57D0", "137333", "1D1D1F", "6E6E73"
N = 4000
LAST = N + 1                                   # data rows 2..4001

COLS = ["employee_id", "hire_date", "exit_date", "exit_type", "department", "country", "job_level", "gender",
        "base_salary_eur", "compa_ratio", "months_since_promotion", "contract_type", "work_model", "engagement_score"]
HELPERS = [  # (header, formula for row r) - every one documented in the sheet's second row
    ("active", 'IF(C{r}="",1,0)', "1 if still employed at 30 June 2026"),
    ("at_risk_1_oct", 'IF(AND(B{r}<DATE(2025,10,1),OR(C{r}="",C{r}>=DATE(2025,10,1))),1,0)',
     "employed on 1 October 2025: the people the driver model is fitted on"),
    ("resigned_after", 'IF(AND(D{r}="Voluntary",C{r}<>""),IF(C{r}>=DATE(2025,10,1),1,0),0)',
     "resigned from 1 October 2025 to 30 June 2026"),
    ("below_band", "IF(J{r}<0.92,1,0)", "compa-ratio under 0.92"),
    ("no_promotion", 'IF(MAX(0,K{r}-((YEAR(IF(C{r}="",DATE(2026,6,30),C{r}))-2025)*12+MONTH(IF(C{r}="",DATE(2026,6,30),C{r}))-10))>24,1,0)',
     "more than 24 months since promotion on 1 October 2025"),
    ("fixed_term", 'IF(L{r}="Fixed-term",1,0)', "fixed-term contract"),
    ("first_year", "IF((2025-YEAR(B{r}))*12+10-MONTH(B{r})<12,1,0)", "under 12 months of tenure on 1 October 2025"),
    ("onsite", 'IF(M{r}="Onsite",1,0)', "fully onsite"),
    ("low_engagement", "IF(N{r}<=Settings!$C$5,1,0)", "engagement in the bottom quartile of all employees"),
    ("customer_service", 'IF(E{r}="Customer Service",1,0)', "works in Customer Service"),
]
SIGNS = [("Paid below band (compa-ratio < 0.92)", "below_band"), ("No promotion in 24+ months", "no_promotion"),
         ("Engagement in bottom quartile", "low_engagement"), ("Fixed-term contract", "fixed_term"),
         ("First year of tenure", "first_year"), ("Fully onsite", "onsite"), ("Works in Customer Service", "customer_service")]


def letter(i: int) -> str:
    s = ""
    i += 1
    while i:
        i, rem = divmod(i - 1, 26)
        s = chr(65 + rem) + s
    return s


COL = {name: letter(i) for i, name in enumerate(COLS + [h for h, _, _ in HELPERS])}


def rng(name: str) -> str:
    return f"Data!${COL[name]}$2:${COL[name]}${LAST}"


def put(ws, ref, value, *, bold=False, color=INK, fmt=None, size=11, italic=False):
    c = ws[ref]
    c.value = value
    c.font = Font(bold=bold, color=color, size=size, italic=italic)
    if fmt:
        c.number_format = fmt
    return c


def head(ws, row, labels, start=1):
    for i, text in enumerate(labels):
        c = ws.cell(row=row, column=start + i, value=text)
        c.font = Font(bold=True)
        c.fill = PatternFill("solid", fgColor="F2F2F7")
        c.alignment = Alignment(wrap_text=True, vertical="top")


def widths(ws, spec):
    for col, w in spec.items():
        ws.column_dimensions[col].width = w


def title(ws, text, sub):
    put(ws, "A1", text, bold=True, size=14)
    put(ws, "A2", sub, color=MUTED, italic=True)


class Builder:
    def __init__(self):
        self.employees = load_employees()
        assert len(self.employees) == N
        self.checks: list[tuple[str, str, object, str]] = []      # area, item, python value, workbook ref
        self.wb = Workbook()

    def check(self, area, item, value, ref):
        self.checks.append((area, item, value, ref))

    # ---------------------------------------------------------------- data
    def data(self):
        ws = self.wb.create_sheet("Data")
        head(ws, 1, COLS + [h for h, _, _ in HELPERS])
        for r, e in enumerate(self.employees, start=2):
            vals = [e["employee_id"], e["hire_dt"], e["exit_dt"], e["exit_type"] or None, e["department"], e["country"],
                    e["job_level"], e["gender"], e["base_salary_eur"], e["compa_ratio"], e["months_since_promotion"],
                    e["contract_type"], e["work_model"], e["engagement_score"]]
            for i, v in enumerate(vals):
                c = ws.cell(row=r, column=i + 1, value=v)
                c.font = Font(color=BLUE)
                if isinstance(v, date):
                    c.number_format = "yyyy-mm-dd"
            for j, (_, formula, _) in enumerate(HELPERS):
                ws.cell(row=r, column=len(COLS) + j + 1, value="=" + formula.format(r=r))
        ws.freeze_panes = "B2"
        for i in range(len(COLS) + len(HELPERS)):
            ws.column_dimensions[letter(i)].width = 14

    def settings(self):
        ws = self.wb.create_sheet("Settings")
        title(ws, "Settings", "Dates and thresholds every sheet reads. Blue cells are inputs.")
        rows = [("Period start", WINDOW_START), ("Snapshot", SNAPSHOT),
                ("Engagement bottom-quartile cut", f"=PERCENTILE({rng('engagement_score')},0.25)"),
                ("Article 10 trigger", 0.05), ("Smallest reportable category", pg.MIN_CATEGORY),
                ("Smallest group per sex", pg.MIN_PER_GENDER)]
        for i, (label, value) in enumerate(rows, start=3):
            put(ws, f"B{i}", label)
            put(ws, f"C{i}", value, color=BLUE if not str(value).startswith("=") else INK,
                fmt="yyyy-mm-dd" if isinstance(value, date) else ("0%" if value == 0.05 else None))
        widths(ws, {"A": 3, "B": 34, "C": 16})
        eng = quantile([e["engagement_score"] for e in self.employees], 0.25)
        self.check("Settings", "Engagement bottom-quartile cut", eng, "Settings!C5")

    # ---------------------------------------------------------------- turnover
    def turnover(self):
        ws = self.wb.create_sheet("Turnover")
        title(ws, "Voluntary turnover by department",
              "Exits over the twelve months to June 2026 as a share of the average of twelve month-end headcounts.")
        ends = []
        for m in range(12):
            y, mo = divmod(WINDOW_START.month - 1 + m, 12)
            nxt_y, nxt_m = divmod(WINDOW_START.month + m, 12)
            ends.append(date(WINDOW_START.year + nxt_y, nxt_m + 1, 1).toordinal() - 1)
        head(ws, 4, ["Department"] + [date.fromordinal(d).strftime("%b %y") for d in ends]
             + ["Average headcount", "Resigned", "Voluntary turnover"])
        for i, d in enumerate(ends):
            put(ws, f"{letter(i + 1)}5", date.fromordinal(d), color=BLUE, fmt="yyyy-mm-dd")
        put(ws, "A5", "month end", color=MUTED, italic=True)
        depts = sorted({e["department"] for e in self.employees})
        rows = depts + ["All departments"]
        for k, dept in enumerate(rows):
            r = 6 + k
            put(ws, f"A{r}", dept, bold=dept == "All departments")
            crit = f'{rng("department")},$A{r},' if dept != "All departments" else ""
            for i in range(12):
                cell = f"{letter(i + 1)}$5"
                ws[f"{letter(i + 1)}{r}"] = (f'=COUNTIFS({crit}{rng("hire_date")},"<="&{cell},{rng("exit_date")},"")'
                                              f'+COUNTIFS({crit}{rng("hire_date")},"<="&{cell},{rng("exit_date")},">"&{cell})')
            put(ws, f"N{r}", f"=AVERAGE(B{r}:M{r})", fmt="#,##0.0")
            put(ws, f"O{r}", f'=COUNTIFS({crit}{rng("exit_type")},"Voluntary")')
            put(ws, f"P{r}", f"=O{r}/N{r}", fmt="0.0%")
            group = [e for e in self.employees if dept == "All departments" or e["department"] == dept]
            avg = sum(monthly_headcount(group)) / 12
            vol = sum(1 for e in group if e["is_voluntary_leaver"])
            self.check("Turnover", f"{dept}: average headcount", avg, f"Turnover!N{r}")
            self.check("Turnover", f"{dept}: resigned", vol, f"Turnover!O{r}")
            self.check("Turnover", f"{dept}: voluntary turnover", vol / avg, f"Turnover!P{r}")
        widths(ws, {"A": 20, **{letter(i + 1): 9 for i in range(12)}, "N": 12, "O": 10, "P": 12})

    # ---------------------------------------------------------------- warning signs
    def signs(self):
        ws = self.wb.create_sheet("Warning signs")
        title(ws, "The warning signs the attrition model is built on",
              "Employed on 1 October 2025, signs as they stood that day, resignations over the next nine months. "
              "The model weighs them together; here each is read on its own.")
        head(ws, 4, ["Sign", "With the sign", "Resigned", "Rate", "Without", "Resigned", "Rate", "Ratio of rates"])
        frame = att.build_model_frame(self.employees, load_cases())
        drivers = att.build_drivers("Customer Service")
        at_risk, resigned = rng("at_risk_1_oct"), rng("resigned_after")
        for k, (label, key) in enumerate(SIGNS):
            r = 5 + k
            sign = rng(key)
            put(ws, f"A{r}", label)
            put(ws, f"B{r}", f"=COUNTIFS({at_risk},1,{sign},1)")
            put(ws, f"C{r}", f"=COUNTIFS({at_risk},1,{sign},1,{resigned},1)")
            put(ws, f"D{r}", f"=C{r}/B{r}", fmt="0.0%")
            put(ws, f"E{r}", f"=COUNTIFS({at_risk},1,{sign},0)")
            put(ws, f"F{r}", f"=COUNTIFS({at_risk},1,{sign},0,{resigned},1)")
            put(ws, f"G{r}", f"=F{r}/E{r}", fmt="0.0%")
            put(ws, f"H{r}", f"=D{r}/G{r}", fmt="0.00")
            test = drivers["Works in Customer Service" if key == "customer_service" else label]
            w = [e for e in frame if test(e)]
            wo = [e for e in frame if not test(e)]
            self.check("Warning signs", f"{label}: with", len(w), f"'Warning signs'!B{r}")
            self.check("Warning signs", f"{label}: resigned with", sum(e["left_in_outcome_window"] for e in w), f"'Warning signs'!C{r}")
            self.check("Warning signs", f"{label}: without", len(wo), f"'Warning signs'!E{r}")
            self.check("Warning signs", f"{label}: resigned without", sum(e["left_in_outcome_window"] for e in wo), f"'Warning signs'!F{r}")
        r = 6 + len(SIGNS)
        put(ws, f"A{r}", "Everyone at risk", bold=True)
        put(ws, f"B{r}", f"=SUM({at_risk})")
        put(ws, f"C{r}", f"=SUMPRODUCT({at_risk},{resigned})")
        put(ws, f"D{r}", f"=C{r}/B{r}", fmt="0.0%")
        self.check("Warning signs", "Everyone at risk", len(frame), f"'Warning signs'!B{r}")
        self.check("Warning signs", "Resigned", sum(e["left_in_outcome_window"] for e in frame), f"'Warning signs'!C{r}")
        put(ws, f"A{r + 2}", "The HR-case sign (a reopened case in the quarter before) needs the case data and is in the report, "
                             "not here.", color=MUTED, italic=True)
        widths(ws, {"A": 40, "B": 13, "C": 10, "D": 9, "E": 10, "F": 10, "G": 9, "H": 13})

    # ---------------------------------------------------------------- pay gap
    def pay(self):
        ws = self.wb.create_sheet("Pay gap")
        title(ws, "The gender pay gap (Directive (EU) 2023/970, Article 9)",
              "Base pay of active employees at 30 June 2026, men as the reference.")
        active = [e for e in self.employees if e["active"]]
        sal, sex, act = rng("base_salary_eur"), rng("gender"), rng("active")
        rows = [
            ("Women", f'=COUNTIFS({sex},"F",{act},1)', sum(e["gender"] == "F" for e in active), None),
            ("Men", f'=COUNTIFS({sex},"M",{act},1)', sum(e["gender"] == "M" for e in active), None),
            ("Mean pay, women", f'=AVERAGEIFS({sal},{sex},"F",{act},1)', None, "#,##0"),
            ("Mean pay, men", f'=AVERAGEIFS({sal},{sex},"M",{act},1)', None, "#,##0"),
            ("Mean gender pay gap", "=(C7-C6)/C7", pg.raw_gap(active) / 100, "0.0%"),
            ("Median pay, women", ("array", f'MEDIAN(IF(({sex}="F")*({act}=1),{sal}))'), None, "#,##0"),
            ("Median pay, men", ("array", f'MEDIAN(IF(({sex}="M")*({act}=1),{sal}))'), None, "#,##0"),
            ("Median gender pay gap", "=(C10-C9)/C10", pg.raw_gap(active, median) / 100, "0.0%"),
        ]
        salaries = [e["base_salary_eur"] for e in active]
        cuts = [quantile(salaries, q) for q in (0.25, 0.5, 0.75)]
        for q, cut in zip((0.25, 0.5, 0.75), cuts):
            rows.append((f"Pay at the {int(q * 100)}th percentile", ("array", f"PERCENTILE(IF({act}=1,{sal}),{q})"), cut, "#,##0"))
        q1 = [e for e in active if e["base_salary_eur"] <= cuts[0]]
        q4 = [e for e in active if e["base_salary_eur"] > cuts[2]]
        rows += [
            ("Women in the lowest quarter", f'=COUNTIFS({sex},"F",{act},1,{sal},"<="&C12)/COUNTIFS({act},1,{sal},"<="&C12)',
             sum(e["gender"] == "F" for e in q1) / len(q1), "0.0%"),
            ("Women in the highest quarter", f'=COUNTIFS({sex},"F",{act},1,{sal},">"&C14)/COUNTIFS({act},1,{sal},">"&C14)',
             sum(e["gender"] == "F" for e in q4) / len(q4), "0.0%"),
        ]
        for i, (label, formula, value, fmt) in enumerate(rows, start=4):
            put(ws, f"B{i}", label)
            if isinstance(formula, tuple):
                ws[f"C{i}"] = ArrayFormula(f"C{i}", "=" + formula[1])
                if fmt:
                    ws[f"C{i}"].number_format = fmt
            else:
                put(ws, f"C{i}", formula, fmt=fmt)
            if value is not None:
                self.check("Pay gap", label, value, f"'Pay gap'!C{i}")
        r0 = 4 + len(rows) + 2
        head(ws, r0, ["", "Country", "Mean gap"], start=1)
        for k, country in enumerate(["DE", "ES", "IT", "PL"]):
            r = r0 + 1 + k
            put(ws, f"B{r}", country)
            m = f'AVERAGEIFS({sal},{sex},"M",{act},1,{rng("country")},B{r})'
            f = f'AVERAGEIFS({sal},{sex},"F",{act},1,{rng("country")},B{r})'
            put(ws, f"C{r}", f"=({m}-{f})/{m}", fmt="0.0%")
            self.check("Pay gap", f"Mean gap, {country}", pg.raw_gap([e for e in active if e["country"] == country]) / 100,
                       f"'Pay gap'!C{r}")
        widths(ws, {"A": 3, "B": 34, "C": 14})

    def categories(self):
        ws = self.wb.create_sheet("Categories")
        title(ws, "Categories of workers (Article 10): department x job level",
              "A category reports when it has at least 30 people and 8 of each sex; at a gap of 5% or more it needs a "
              "justification or a remedy, or a joint pay assessment follows.")
        head(ws, 4, ["Department", "Level", "Employees", "Women", "Men", "Mean gap", "Reportable", "At or above 5%"])
        active = [e for e in self.employees if e["active"]]
        reported = {name: (gap, n) for name, gap, n, _ in pg.category_gaps(active)}
        sal, sex, act, dep, lev = rng("base_salary_eur"), rng("gender"), rng("active"), rng("department"), rng("job_level")
        r = 5
        for dept in sorted({e["department"] for e in active}):
            for level in pg.LEVEL_ORDER:
                put(ws, f"A{r}", dept)
                put(ws, f"B{r}", level)
                base = f"{act},1,{dep},A{r},{lev},B{r}"
                put(ws, f"C{r}", f"=COUNTIFS({base})")
                put(ws, f"D{r}", f'=COUNTIFS({base},{sex},"F")')
                put(ws, f"E{r}", f'=COUNTIFS({base},{sex},"M")')
                m, f = f'AVERAGEIFS({sal},{base},{sex},"M")', f'AVERAGEIFS({sal},{base},{sex},"F")'
                put(ws, f"F{r}", f'=IF(AND(D{r}>0,E{r}>0),({m}-{f})/{m},"")', fmt="0.0%")
                put(ws, f"G{r}", f'=IF(AND(C{r}>=Settings!$C$7,D{r}>=Settings!$C$8,E{r}>=Settings!$C$8),"Yes","No")')
                put(ws, f"H{r}", f'=IF(AND(G{r}="Yes",F{r}>=Settings!$C$6),"Yes","No")')
                key = f"{dept} - {level}"
                if key in reported:
                    gap, n = reported[key]
                    self.check("Categories", f"{key}: employees", n, f"Categories!C{r}")
                    self.check("Categories", f"{key}: mean gap", gap / 100, f"Categories!F{r}")
                r += 1
        put(ws, f"A{r + 1}", "Reportable categories", bold=True)
        put(ws, f"C{r + 1}", f'=COUNTIF(G5:G{r - 1},"Yes")')
        put(ws, f"A{r + 2}", "At or above the trigger", bold=True)
        put(ws, f"C{r + 2}", f'=COUNTIF(H5:H{r - 1},"Yes")')
        self.check("Categories", "Reportable categories", len(reported), f"Categories!C{r + 1}")
        self.check("Categories", "At or above the trigger", sum(1 for g, _ in reported.values() if g >= pg.THRESHOLD),
                   f"Categories!C{r + 2}")
        widths(ws, {"A": 20, "B": 8, "C": 11, "D": 9, "E": 9, "F": 10, "G": 12, "H": 14})

    # ---------------------------------------------------------------- reconciliation and cover
    def reconciliation(self):
        ws = self.wb.create_sheet("Reconciliation")
        title(ws, "Reconciliation: workbook formulas against the Python pipeline",
              "Column D was written by tools/build_workbook.py from the Python results; column E is the live formula.")
        head(ws, 6, ["Area", "Item", "", "Python value", "Workbook value", "Difference", "Match"])
        first, last = 7, 6 + len(self.checks)
        put(ws, "B3", (f'=IF(COUNTIF(G{first}:G{last},"No")=0,"All "&COUNTA(B{first}:B{last})&" checks match",'
                       f'COUNTIF(G{first}:G{last},"No")&" of "&COUNTA(B{first}:B{last})&" checks do not match")'),
            bold=True, size=12)
        for r, (area, item, value, ref) in enumerate(self.checks, start=first):
            put(ws, f"A{r}", area)
            put(ws, f"B{r}", item)
            fmt = "0.000000" if isinstance(value, float) else None
            put(ws, f"D{r}", value, color=BLUE, fmt=fmt)
            put(ws, f"E{r}", f"={ref}", color=GREEN, fmt=fmt)
            put(ws, f"F{r}", f'=IF(AND(ISNUMBER(D{r}),ISNUMBER(E{r})),E{r}-D{r},"")', fmt="0.0E+00")
            put(ws, f"G{r}", (f'=IF(AND(ISNUMBER(D{r}),ISNUMBER(E{r})),IF(ABS(E{r}-D{r})<=1E-9*MAX(1,ABS(D{r})),"Yes","No"),'
                              f'IF(D{r}=E{r},"Yes","No"))'))
        for text, colour in (("Yes", "D5ECDC"), ("No", "F5C6C2")):
            ws.conditional_formatting.add(f"G{first}:G{last}", CellIsRule(operator="equal", formula=[f'"{text}"'],
                                                                         fill=PatternFill("solid", fgColor=colour)))
        ws.freeze_panes = "A7"
        widths(ws, {"A": 16, "B": 52, "C": 3, "D": 16, "E": 16, "F": 12, "G": 8})

    def cover(self):
        ws = self.wb.active
        ws.title = "Cover"
        widths(ws, {"A": 3, "B": 22, "C": 100})
        put(ws, "B2", "People analytics: the core figures, as formulas", bold=True, size=18)
        put(ws, "B3", "A synthetic organisation of 4,000 employees in Italy, Poland, Germany and Spain, July 2025 to June 2026",
            color=MUTED, size=12)
        purpose = {
            "Turnover": "Voluntary turnover by department, from twelve month-end headcounts counted on the Data sheet.",
            "Warning signs": "The signs the attrition model is built on, and how often people with and without each resigned.",
            "Pay gap": "The Article 9 items: mean and median gap, pay quarters, the gap by country.",
            "Categories": "Department x level, with the Article 10 size rules and the 5% trigger.",
            "Data": "One row per employee: inputs in blue, helper flags as formulas, each explained in this file's README.",
            "Settings": "Dates and thresholds the formulas read.",
            "Reconciliation": "Every figure above checked against the Python pipeline that writes the report.",
        }
        put(ws, "B5", "Sheets", bold=True)
        for i, (name, text) in enumerate(purpose.items(), start=6):
            put(ws, f"B{i}", name, color=GREEN)
            put(ws, f"C{i}", text)
        put(ws, "B14", "Check", bold=True)
        put(ws, "C14", "=Reconciliation!B3", bold=True, color=GREEN)
        put(ws, "B16", "Colours", bold=True)
        for i, (label, meaning, colour) in enumerate([("Blue", "an input", BLUE), ("Black", "a formula", INK),
                                                      ("Green", "a link to another sheet", GREEN)], start=17):
            put(ws, f"B{i}", label, color=colour)
            put(ws, f"C{i}", meaning)
        put(ws, "B21", "The data is synthetic. Generated by src/generate_data.py with a fixed seed.", color=MUTED, italic=True)

    def build(self) -> Path:
        self.cover()
        self.turnover()
        self.signs()
        self.pay()
        self.categories()
        self.data()
        self.settings()
        self.reconciliation()
        OUT.parent.mkdir(exist_ok=True)
        self.wb.save(OUT)
        from excel_twin.determinism import normalise
        normalise(OUT)
        return OUT


if __name__ == "__main__":
    b = Builder()
    path = b.build()
    print(f"{path.relative_to(ROOT)}: {len(b.checks)} figures to reconcile")
