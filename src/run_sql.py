"""
Run the analysis queries in sql/ and print the results as text tables.

Each .sql file holds several queries, each introduced by a `-- name:` comment
and a short `-- ?` question in plain English. Usage:

    python3 src/run_sql.py            # every file
    python3 src/run_sql.py 02         # only files whose name starts with 02
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "hr.db"
SQL_DIR = ROOT / "sql"
MAX_ROWS = 15


def split_queries(text: str) -> list[tuple[str, str, str]]:
    """Split a .sql file into (name, question, sql) blocks."""
    blocks = []
    name = question = None
    buffer: list[str] = []
    for line in text.splitlines():
        if line.startswith("-- name:"):
            if name:
                blocks.append((name, question or "", "\n".join(buffer).strip()))
            name, question, buffer = line.split(":", 1)[1].strip(), None, []
        elif line.startswith("-- ?"):
            question = line[4:].strip()
        else:
            buffer.append(line)
    if name:
        blocks.append((name, question or "", "\n".join(buffer).strip()))
    return blocks


def print_table(headers: list[str], rows: list[tuple]) -> None:
    if not rows:
        print("   (no rows)")
        return
    shown = rows[:MAX_ROWS]
    cells = [[("" if v is None else f"{v:,.2f}".rstrip("0").rstrip(".")
               if isinstance(v, float) else str(v)) for v in row] for row in shown]
    widths = [max(len(h), *(len(c[i]) for c in cells)) for i, h in enumerate(headers)]
    print("   " + "  ".join(h.ljust(w) for h, w in zip(headers, widths)))
    print("   " + "  ".join("-" * w for w in widths))
    for row in cells:
        print("   " + "  ".join(v.rjust(w) if v.replace(",", "").replace("-", "")
                                .replace(".", "").isdigit() else v.ljust(w)
                                for v, w in zip(row, widths)))
    if len(rows) > MAX_ROWS:
        print(f"   ... {len(rows) - MAX_ROWS:,} more rows")


def main() -> None:
    if not DB.exists():
        sys.exit("data/hr.db not found - run `python3 src/build_db.py` first")

    prefix = sys.argv[1] if len(sys.argv) > 1 else ""
    files = sorted(f for f in SQL_DIR.glob("*.sql") if f.name.startswith(prefix))

    with sqlite3.connect(DB) as conn:
        for path in files:
            print(f"\n{'=' * 78}\n{path.name}\n{'=' * 78}")
            for name, question, sql in split_queries(path.read_text(encoding="utf-8")):
                print(f"\n-- {name}")
                if question:
                    print(f"   {question}")
                cur = conn.execute(sql)
                print_table([d[0] for d in cur.description], cur.fetchall())


if __name__ == "__main__":
    main()
