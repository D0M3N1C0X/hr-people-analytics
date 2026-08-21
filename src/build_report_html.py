"""
Render reports/findings.md as a single self-contained HTML report.

The Markdown report is the source of truth; this turns it into something a
reader can open in a browser, with all 13 charts inlined as SVG so the file
travels on its own - no image folder, no network, no build step.

    python3 src/build_report_html.py                     -> reports/findings.html
    python3 src/build_report_html.py --fragment [PATH]   -> body-only variant

The fragment form omits the <html>/<head>/<body> wrapper for hosts that supply
their own page skeleton.
"""

from __future__ import annotations

import html
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
SOURCE = REPORTS / "findings.md"

TITLE = "People Analytics FY2026"

STYLE = """
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@500&family=IBM+Plex+Sans:wght@400;500;600&family=Source+Serif+4:opsz,wght@8..60,400;8..60,600&display=swap">
<style>
:root{
  --paper:#fbfcfd; --surface:#ffffff; --ink:#131a24; --ink-soft:#39434f; --muted:#5f6b7a;
  --line:#e2e7ef; --line-strong:#c9d2df; --accent:#1d4ed8; --accent-wash:#eef3ff;
  --flag:#b5352c; --flag-wash:#fdeceb; --ok:#0c6b59; --ok-wash:#e8f5f1;
  --plate:#ffffff; --plate-edge:#dde4ee; --shadow:0 1px 2px rgba(19,26,36,.06),0 8px 24px rgba(19,26,36,.06);
}
@media (prefers-color-scheme: dark){
  :root:not([data-theme="light"]){
    --paper:#0f141b; --surface:#161d26; --ink:#e7ecf3; --ink-soft:#c3cbd6; --muted:#8b97a6;
    --line:#232c38; --line-strong:#33404f; --accent:#7ba4ff; --accent-wash:#17233a;
    --flag:#f08a80; --flag-wash:#2e1b1a; --ok:#5fc6ae; --ok-wash:#12291f;
    --plate:#ffffff; --plate-edge:#2b3542; --shadow:0 1px 2px rgba(0,0,0,.4),0 10px 30px rgba(0,0,0,.35);
  }
}
:root[data-theme="dark"]{
  --paper:#0f141b; --surface:#161d26; --ink:#e7ecf3; --ink-soft:#c3cbd6; --muted:#8b97a6;
  --line:#232c38; --line-strong:#33404f; --accent:#7ba4ff; --accent-wash:#17233a;
  --flag:#f08a80; --flag-wash:#2e1b1a; --ok:#5fc6ae; --ok-wash:#12291f;
  --plate:#ffffff; --plate-edge:#2b3542; --shadow:0 1px 2px rgba(0,0,0,.4),0 10px 30px rgba(0,0,0,.35);
}

*{box-sizing:border-box}
body{
  margin:0; background:var(--paper); color:var(--ink);
  font-family:"IBM Plex Sans",-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  font-size:17px; line-height:1.68; -webkit-font-smoothing:antialiased;
}
.page{padding:clamp(1.25rem,4vw,3.5rem) clamp(1rem,4vw,2rem) 5rem}
.doc{display:grid; gap:1.5rem; justify-items:center}
.doc > *{width:100%; max-width:42rem; margin:0}
.doc > figure, .doc > .table-wrap{max-width:57rem}

h1,h2,h3{font-family:"Source Serif 4",Georgia,"Times New Roman",serif; text-wrap:balance; margin:0}
h1{font-size:clamp(2.1rem,5.5vw,3.1rem); font-weight:600; letter-spacing:-.015em; line-height:1.12}
h2{font-size:clamp(1.5rem,3.4vw,2rem); font-weight:600; letter-spacing:-.01em;
   display:flex; align-items:baseline; gap:.75rem; padding-top:2.5rem;
   border-top:1px solid var(--line); margin-top:1.5rem}
h2 .num{
  font-family:"IBM Plex Mono",ui-monospace,SFMono-Regular,Menlo,monospace; font-size:.8rem;
  font-weight:500; color:var(--accent); letter-spacing:.08em; transform:translateY(-.15em);
}
h3{font-size:1.22rem; font-weight:600; padding-top:1.25rem}
p{margin:0; color:var(--ink-soft)}
strong{color:var(--ink); font-weight:600}
a{color:var(--accent); text-decoration:underline; text-underline-offset:2px; text-decoration-thickness:1px}
a:focus-visible{outline:2px solid var(--accent); outline-offset:3px; border-radius:2px}

.masthead{border-bottom:2px solid var(--ink); padding-bottom:1.5rem}
.eyebrow{
  font-family:"IBM Plex Mono",ui-monospace,monospace; font-size:.72rem; letter-spacing:.16em;
  text-transform:uppercase; color:var(--muted); margin-bottom:1rem
}
dl.meta{display:grid; grid-template-columns:auto 1fr; gap:.4rem 1.25rem; margin:1.4rem 0 0; font-size:.94rem}
dl.meta dt{
  font-family:"IBM Plex Mono",ui-monospace,monospace; font-size:.72rem; letter-spacing:.1em;
  text-transform:uppercase; color:var(--muted); padding-top:.28em
}
dl.meta dd{margin:0; color:var(--ink-soft)}

.notice{
  background:var(--accent-wash); border-left:3px solid var(--accent); border-radius:0 4px 4px 0;
  padding:1rem 1.25rem; font-size:.95rem; color:var(--ink-soft)
}
p.note{font-size:.9rem; color:var(--muted)}

figure{display:flex; flex-direction:column; gap:.6rem}
figure .plate{
  background:var(--plate); border:1px solid var(--plate-edge); border-radius:6px;
  box-shadow:var(--shadow); padding:.5rem; overflow-x:auto
}
figure svg{display:block; width:100%; height:auto; min-width:32rem}
figcaption{
  font-family:"IBM Plex Mono",ui-monospace,monospace; font-size:.72rem; letter-spacing:.06em;
  color:var(--muted); text-transform:uppercase
}

.table-wrap{overflow-x:auto; border:1px solid var(--line); border-radius:6px; background:var(--surface)}
table{border-collapse:collapse; width:100%; font-size:.92rem; font-variant-numeric:tabular-nums}
th,td{padding:.62rem .9rem; text-align:left; border-bottom:1px solid var(--line)}
thead th{
  font-family:"IBM Plex Mono",ui-monospace,monospace; font-size:.68rem; font-weight:500;
  letter-spacing:.09em; text-transform:uppercase; color:var(--muted);
  border-bottom:1px solid var(--line-strong); white-space:nowrap
}
tbody tr:last-child td{border-bottom:none}
td.r,th.r{text-align:right}
td.r{font-family:"IBM Plex Mono",ui-monospace,monospace; font-size:.86rem}

.pill{
  display:inline-block; padding:.14em .6em; border-radius:999px; font-size:.72rem;
  font-weight:600; letter-spacing:.02em; white-space:nowrap
}
.pill.flag{background:var(--flag-wash); color:var(--flag)}
.pill.ok{background:var(--ok-wash); color:var(--ok)}

code{
  font-family:"IBM Plex Mono",ui-monospace,SFMono-Regular,Menlo,monospace; font-size:.86em;
  background:var(--accent-wash); color:var(--ink); padding:.1em .35em; border-radius:3px
}
ol{margin:0; padding-left:1.3rem; display:grid; gap:.75rem; color:var(--ink-soft)}
ol li::marker{color:var(--accent); font-family:"IBM Plex Mono",ui-monospace,monospace; font-size:.85em}
hr{border:none; height:1px; background:var(--line); margin:1rem 0}

footer.colophon{
  max-width:42rem; margin:3rem auto 0; padding-top:1.25rem; border-top:1px solid var(--line);
  font-size:.85rem; color:var(--muted)
}
@media (max-width:640px){
  body{font-size:16px}
  dl.meta{grid-template-columns:1fr; gap:.15rem}
  dl.meta dd{margin-bottom:.5rem}
}
</style>
"""

COLOPHON = ('<footer class="colophon">Generated from <code>reports/findings.md</code> by '
            '<code>python3 src/build_report_html.py</code>. Synthetic data, fixed seed - '
            'no real employee records. Charts are inline SVG; this file has no external '
            'dependencies beyond its webfonts.</footer>')


# --------------------------------------------------------------------------
# Inline markdown
# --------------------------------------------------------------------------

def inline(text: str) -> str:
    out = html.escape(text, quote=False)
    out = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', out)
    out = re.sub(r"`([^`]+)`", r"<code>\1</code>", out)
    out = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", out)
    out = re.sub(r"(?<![\w*])\*([^*]+)\*(?![\w*])", r"<em>\1</em>", out)
    out = out.replace(" - ", " &ndash; ")
    return out


def cell(text: str, align: str) -> str:
    klass = ' class="r"' if align == "r" else ""
    if "Above trigger" in text or "JOINT PAY" in text:
        return f"<td{klass}><span class=\"pill flag\">{inline(text).replace('<strong>', '').replace('</strong>', '')}</span></td>"
    if "Within tolerance" in text:
        return f'<td{klass}><span class="pill ok">{inline(text)}</span></td>'
    return f"<td{klass}>{inline(text)}</td>"


def parse_table(rows: list[str]) -> str:
    def split(row: str) -> list[str]:
        return [c.strip() for c in row.strip().strip("|").split("|")]

    headers = split(rows[0])
    # `---:` means right-aligned; `:---` and `:---:` do not.
    aligns = ["r" if c.strip().endswith(":") and not c.strip().startswith(":") else "l"
              for c in split(rows[1])]
    body = []
    for row in rows[2:]:
        cells = split(row)
        body.append("<tr>" + "".join(cell(c, aligns[i] if i < len(aligns) else "l")
                                     for i, c in enumerate(cells)) + "</tr>")
    head = "".join(f'<th{" class=\"r\"" if aligns[i] == "r" else ""}>{inline(h)}</th>'
                   for i, h in enumerate(headers))
    return ('<div class="table-wrap"><table><thead><tr>' + head + "</tr></thead><tbody>"
            + "".join(body) + "</tbody></table></div>")


def figure(alt: str, src: str) -> str:
    svg_path = REPORTS / src
    if not svg_path.exists():
        return f'<p class="note">[missing figure: {html.escape(src)}]</p>'
    svg = svg_path.read_text(encoding="utf-8")
    svg = re.sub(r'\s(width|height)="\d+"', "", svg, count=2)
    return (f'<figure><div class="plate">{svg}</div>'
            f"<figcaption>{html.escape(alt)}</figcaption></figure>")


def paragraph(lines: list[str]) -> str:
    text = "\n".join(lines).strip()
    if not text:
        return ""
    # A run of "**Label:** value" entries becomes the masthead metadata list,
    # even where the source wraps a value across several lines.
    if re.match(r"^\*\*[^*]+:\*\*", text) and text.count("**") >= 4:
        parts = re.split(r"\*\*([^*]+):\*\*", text)
        items = [f"<dt>{inline(label)}</dt><dd>{inline(' '.join(value.split()))}</dd>"
                 for label, value in zip(parts[1::2], parts[2::2])]
        return '<dl class="meta">' + "".join(items) + "</dl>"
    if text.startswith("*") and text.endswith("*") and not text.startswith("**"):
        return f'<p class="note">{inline(text.strip("*"))}</p>'
    return f"<p>{inline(text)}</p>"


def convert(md: str) -> str:
    out: list[str] = []
    buf: list[str] = []
    table: list[str] = []
    quote: list[str] = []
    olist: list[str] = []

    def flush() -> None:
        nonlocal buf, table, quote, olist
        if buf:
            out.append(paragraph(buf))
            buf = []
        if table:
            out.append(parse_table(table))
            table = []
        if quote:
            out.append(f'<div class="notice">{inline(" ".join(quote))}</div>')
            quote = []
        if olist:
            out.append("<ol>" + "".join(f"<li>{inline(i)}</li>" for i in olist) + "</ol>")
            olist = []

    for raw in md.splitlines():
        line = raw.rstrip()

        if line.startswith("|"):
            flush() if (buf or quote or olist) else None
            table.append(line)
            continue
        if line.startswith("> "):
            flush() if (buf or table or olist) else None
            quote.append(line[2:])
            continue
        if re.match(r"^\d+\.\s", line):
            flush() if (buf or table or quote) else None
            olist.append(re.sub(r"^\d+\.\s", "", line))
            continue

        if not line.strip() or line.strip() == "---":
            flush()
            continue
        if not line.startswith(("#", "![")):
            buf.append(line)
            continue

        flush()

        if line.startswith("!["):
            m = re.match(r"!\[([^\]]*)\]\(([^)]+)\)", line)
            if m:
                out.append(figure(m.group(1), m.group(2)))
            continue
        if line.startswith("### "):
            out.append(f"<h3>{inline(line[4:])}</h3>")
            continue
        if line.startswith("## "):
            heading = line[3:]
            m = re.match(r"^(\d+)\.\s+(.*)$", heading)
            if m:
                out.append(f'<h2><span class="num">{int(m.group(1)):02d}</span>'
                           f"<span>{inline(m.group(2))}</span></h2>")
            else:
                out.append(f"<h2><span>{inline(heading)}</span></h2>")
            continue
        if line.startswith("# "):
            out.append('<header class="masthead"><p class="eyebrow">Workforce report '
                       "&middot; 12 months to 30 June 2026</p>"
                       f"<h1>{inline(line[2:])}</h1>")
            out.append("__CLOSE_MASTHEAD__")
            continue

    flush()

    body = "\n".join(b for b in out if b)
    # the metadata list belongs inside the masthead, everything after it does not
    body = body.replace("__CLOSE_MASTHEAD__\n<dl", "<dl").replace("</dl>", "</dl></header>", 1)
    body = body.replace("__CLOSE_MASTHEAD__", "</header>")
    return body


def main() -> None:
    fragment = "--fragment" in sys.argv
    body = convert(SOURCE.read_text(encoding="utf-8"))
    content = (f"<title>{TITLE}</title>{STYLE}"
               f'<div class="page"><article class="doc">{body}</article>{COLOPHON}</div>')

    if fragment:
        args = [a for a in sys.argv[1:] if not a.startswith("--")]
        target = Path(args[0]) if args else REPORTS / "findings.fragment.html"
        target.write_text(content, encoding="utf-8")
    else:
        target = REPORTS / "findings.html"
        target.write_text('<!doctype html><html lang="en"><head><meta charset="utf-8">'
                          '<meta name="viewport" content="width=device-width,initial-scale=1">'
                          f"{content.split('<div class=\"page\">')[0]}</head><body>"
                          f'<div class="page">{content.split("<div class=\"page\">")[1]}'
                          "</body></html>", encoding="utf-8")

    shown = target.relative_to(ROOT) if target.is_relative_to(ROOT) else target
    print(f"     {shown}  ({target.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
