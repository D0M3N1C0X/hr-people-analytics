"""
Load the two CSVs into a small SQLite warehouse (data/hr.db).

Kept deliberately explicit - typed columns, indexes, one view - so the .sql
files in sql/ read like queries against a real HR data mart rather than
against a spreadsheet.
"""

from __future__ import annotations

import csv
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "hr.db"

SCHEMA = """
DROP TABLE IF EXISTS employees;
CREATE TABLE employees (
    employee_id             TEXT PRIMARY KEY,
    hire_date               TEXT NOT NULL,
    exit_date               TEXT,
    exit_type               TEXT,
    exit_reason             TEXT,
    country                 TEXT NOT NULL,
    site                    TEXT NOT NULL,
    department              TEXT NOT NULL,
    job_level               TEXT NOT NULL,
    gender                  TEXT NOT NULL,
    age                     INTEGER,
    contract_type           TEXT,
    work_model              TEXT,
    fte                     REAL,
    base_salary_eur         REAL,
    salary_band_mid_eur     REAL,
    compa_ratio             REAL,
    tenure_months           INTEGER,
    months_since_promotion  INTEGER,
    performance_rating      INTEGER,
    engagement_score        INTEGER
);

DROP TABLE IF EXISTS hr_cases;
CREATE TABLE hr_cases (
    case_id                   TEXT PRIMARY KEY,
    employee_id               TEXT NOT NULL REFERENCES employees(employee_id),
    created_date              TEXT NOT NULL,
    resolved_date             TEXT,
    country                   TEXT,
    department                TEXT,
    category                  TEXT,
    priority                  TEXT,
    channel                   TEXT,
    agent_id                  TEXT,
    agent_tenure_months       INTEGER,
    sla_target_hours          INTEGER,
    resolution_hours          REAL,
    sla_met                   INTEGER,
    first_contact_resolution  INTEGER,
    reopened                  INTEGER,
    csat                      INTEGER
);

CREATE INDEX idx_cases_employee ON hr_cases(employee_id);
CREATE INDEX idx_cases_created  ON hr_cases(created_date);
CREATE INDEX idx_cases_category ON hr_cases(category);
CREATE INDEX idx_emp_department ON employees(department);

DROP VIEW IF EXISTS v_active_employees;
CREATE VIEW v_active_employees AS
    SELECT * FROM employees WHERE exit_date IS NULL OR exit_date = '';
"""


def load_table(conn: sqlite3.Connection, table: str, csv_path: Path) -> int:
    with csv_path.open(encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        columns = reader.fieldnames or []
        rows = [tuple(r[c] if r[c] != "" else None for c in columns) for r in reader]
    placeholders = ",".join("?" * len(columns))
    conn.executemany(
        f"INSERT INTO {table} ({','.join(columns)}) VALUES ({placeholders})", rows)
    return len(rows)


def main() -> None:
    DB.parent.mkdir(parents=True, exist_ok=True)
    if DB.exists():
        DB.unlink()

    with sqlite3.connect(DB) as conn:
        conn.executescript(SCHEMA)
        n_emp = load_table(conn, "employees", DB.parent / "employees.csv")
        n_cases = load_table(conn, "hr_cases", DB.parent / "hr_cases.csv")
        conn.commit()

    print(f"data/hr.db     : employees {n_emp:,} rows, hr_cases {n_cases:,} rows")


if __name__ == "__main__":
    main()
