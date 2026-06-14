#!/usr/bin/env python3
"""Build the fillable questionnaire from fragenkatalog.json.

Reads the structured catalogue (sections -> questions with field_type,
options, description, onsite) and produces three deliverables next to it:
  - fragenkatalog.pdf  : fillable PDF form (AcroForm: radios, checkboxes, text fields)
  - fragenkatalog.html : clickable HTML form
  - fragenkatalog.md   : plain-text catalogue (source of truth, human-readable)

Usage:  python scripts/build_fragenkatalog_form.py
"""
import json
import os
import sys
import html as _html

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.normpath(os.path.join(HERE, "..", "docs", "developer", "analysis"))
JSON_PATH = sys.argv[1] if len(sys.argv) > 1 else os.path.join(OUT, "fragenkatalog.json")
BASE = sys.argv[2] if len(sys.argv) > 2 else "fragenkatalog"

with open(JSON_PATH, encoding="utf-8") as fh:
    DATA = json.load(fh)
SECTIONS = DATA["sections"]


def field_label(q):
    ft = q["field_type"]
    return {
        "ja_nein": "Ja/Nein",
        "auswahl_einfach": "Eine Option ankreuzen",
        "auswahl_mehrfach": "Mehrere ankreuzbar",
        "zahl": "Zahl",
        "text": "Text",
    }.get(ft, ft)


# ----------------------------------------------------------------------------
# 1) Markdown
# ----------------------------------------------------------------------------
def build_md():
    L = [
        "# Fragenkatalog — Gebäudespezifische Kostenkalkulation",
        "",
        "> Aus Report A + B abgeleitet und in klare, einzeln beantwortbare Fragen "
        "zerlegt. **Ausfüllbare Fassung:** `fragenkatalog.pdf` (im PDF anklickbar) "
        "oder `fragenkatalog.html` (im Browser). **✎** = nur vor Ort feststellbar.",
        "",
    ]
    for sec in SECTIONS:
        L.append(f"## {sec['title']}")
        L.append("")
        for q in sec["questions"]:
            mark = " ✎" if q.get("onsite") else ""
            L.append(f"**{q['id']}{mark} {q['question']}**")
            if q.get("description"):
                L.append(f"_{q['description']}_")
            opts = q.get("options") or []
            if opts:
                L.append(f"`[{field_label(q)}]` " + " · ".join(opts))
            else:
                L.append(f"`[{field_label(q)}]`")
            L.append("")
    with open(os.path.join(OUT, BASE + ".md"), "w", encoding="utf-8") as f:
        f.write("\n".join(L))


# ----------------------------------------------------------------------------
# 2) HTML form
# ----------------------------------------------------------------------------
def build_html():
    def esc(s):
        return _html.escape(s or "")

    rows = []
    for sec in SECTIONS:
        rows.append(f'<h2>{esc(sec["title"])}</h2>')
        for q in sec["questions"]:
            mark = ' <span class="on">✎</span>' if q.get("onsite") else ""
            rows.append('<div class="q">')
            rows.append(f'<div class="qt">{esc(q["id"])}{mark} {esc(q["question"])}</div>')
            if q.get("description"):
                rows.append(f'<div class="d">{esc(q["description"])}</div>')
            ft = q["field_type"]
            name = esc(q["id"])
            opts = q.get("options") or []
            if ft == "ja_nein":
                opts = ["Ja", "Nein"]
                ft = "auswahl_einfach"
            if ft == "auswahl_einfach":
                for o in opts:
                    rows.append(
                        f'<label class="opt"><input type="radio" name="{name}" '
                        f'value="{esc(o)}"> {esc(o)}</label>'
                    )
            elif ft == "auswahl_mehrfach":
                for i, o in enumerate(opts):
                    rows.append(
                        f'<label class="opt"><input type="checkbox" name="{name}_{i}" '
                        f'value="{esc(o)}"> {esc(o)}</label>'
                    )
            elif ft == "zahl":
                rows.append(f'<input class="num" type="number" step="any" name="{name}">')
            else:
                rows.append(f'<textarea class="txt" name="{name}" rows="2"></textarea>')
            rows.append("</div>")
    body = "\n".join(rows)
    htmldoc = f"""<!DOCTYPE html><html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Fragenkatalog — Gebäudespezifische Kostenkalkulation</title>
<style>
:root{{--ink:#1a2230;--muted:#5b6876;--line:#d9e0e8;--accent:#1f6feb;--warn:#9a6700;--soft:#f5f8fb}}
body{{font:15px/1.5 system-ui,Segoe UI,Arial,sans-serif;color:var(--ink);max-width:820px;margin:0 auto;padding:24px}}
h1{{font-size:1.5rem;margin:0 0 4px}}h2{{font-size:1.1rem;border-top:2px solid var(--ink);margin-top:26px;padding-top:10px}}
.lead{{color:var(--muted);font-size:.92rem}}
.q{{background:var(--soft);border:1px solid var(--line);border-radius:8px;padding:12px 14px;margin:10px 0}}
.qt{{font-weight:600}}.d{{color:var(--muted);font-size:.86rem;margin:4px 0 8px}}
.on{{color:var(--warn);font-weight:700}}
label.opt{{display:block;margin:3px 0;cursor:pointer}}
input.num{{width:160px;padding:6px;border:1px solid var(--line);border-radius:6px}}
textarea.txt{{width:100%;padding:6px;border:1px solid var(--line);border-radius:6px;font:inherit}}
.actions{{position:sticky;bottom:0;background:#fff;border-top:1px solid var(--line);padding:10px 0;margin-top:20px}}
button{{background:var(--accent);color:#fff;border:0;border-radius:7px;padding:9px 16px;font-weight:600;cursor:pointer}}
@media print{{.actions{{display:none}}body{{max-width:none}}}}
</style></head><body>
<h1>Fragenkatalog — Gebäudespezifische Kostenkalkulation</h1>
<p class="lead">LoRaWAN-Einzelraumregelung · Erhebungsbogen für ein konkretes Gebäude.
Anklicken bzw. eintragen; <span class="on">✎</span> = nur vor Ort feststellbar.
Über „Drucken → Als PDF speichern" entsteht ein ausgefülltes PDF.</p>
<form>
{body}
<div class="actions"><button type="button" onclick="window.print()">Drucken / als PDF speichern</button></div>
</form></body></html>"""
    with open(os.path.join(OUT, BASE + ".html"), "w", encoding="utf-8") as f:
        f.write(htmldoc)


# ----------------------------------------------------------------------------
# 3) Fillable PDF (reportlab AcroForm)
# ----------------------------------------------------------------------------
def build_pdf():
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.colors import HexColor, white, black
    from reportlab.pdfgen import canvas
    from reportlab.lib.utils import simpleSplit

    W, H = A4
    LM, RM, TM, BM = 44, 44, 52, 46
    CW = W - LM - RM
    INK = HexColor("#1a2230")
    MUT = HexColor("#5b6876")
    WARN = HexColor("#9a6700")
    LINE = HexColor("#c4ccd6")
    SOFT = HexColor("#eef2f6")

    c = canvas.Canvas(os.path.join(OUT, BASE + ".pdf"), pagesize=A4)
    c.setTitle("Fragenkatalog — Gebäudespezifische Kostenkalkulation")
    form = c.acroForm
    state = {"y": H - TM, "page": 1}

    def footer():
        c.setFont("Helvetica", 7.5)
        c.setFillColor(MUT)
        c.drawString(LM, 28, "whz-lora · Fragenkatalog · ausfüllbar (Felder anklicken / eintragen)")
        c.drawRightString(W - RM, 28, f"Seite {state['page']}")

    def newpage():
        footer()
        c.showPage()
        state["page"] += 1
        state["y"] = H - TM

    def need(h):
        if state["y"] - h < BM:
            newpage()

    def lines(txt, font, size):
        return simpleSplit(txt or "", font, size, CW - 6)

    def draw_lines(ls, font, size, color, lead, x=LM):
        c.setFont(font, size)
        c.setFillColor(color)
        for ln in ls:
            c.drawString(x, state["y"] - size, ln)
            state["y"] -= lead

    # header
    c.setFont("Helvetica-Bold", 17)
    c.setFillColor(INK)
    c.drawString(LM, state["y"] - 17, "Fragenkatalog — Gebäudespezifische Kostenkalkulation")
    state["y"] -= 24
    c.setFont("Helvetica", 9.5)
    c.setFillColor(MUT)
    for ln in simpleSplit("LoRaWAN-Einzelraumregelung · Erhebungsbogen für ein konkretes Gebäude. "
                          "Felder direkt im PDF anklicken bzw. eintragen. ✎ = nur vor Ort feststellbar.",
                          "Helvetica", 9.5, CW):
        c.drawString(LM, state["y"] - 9.5, ln)
        state["y"] -= 12
    state["y"] -= 6
    c.setStrokeColor(INK)
    c.setLineWidth(1.4)
    c.line(LM, state["y"], W - RM, state["y"])
    state["y"] -= 16

    def opt_height(q):
        ft = q["field_type"]
        if ft == "ja_nein":
            return 18
        if ft in ("auswahl_einfach", "auswahl_mehrfach"):
            return 17 * max(1, len(q.get("options") or []))
        if ft == "zahl":
            return 22
        return 30

    for sec in SECTIONS:
        ql = simpleSplit(sec["title"], "Helvetica-Bold", 12, CW)
        need(20 + 14 * len(ql))
        state["y"] -= 6
        c.setStrokeColor(LINE)
        c.setLineWidth(0.6)
        c.line(LM, state["y"], W - RM, state["y"])
        state["y"] -= 4
        draw_lines(ql, "Helvetica-Bold", 12, INK, 15)
        state["y"] -= 3

        for q in sec["questions"]:
            mark = "  ✎" if q.get("onsite") else ""
            qtext = f"{q['id']}{mark}  {q['question']}"
            qls = lines(qtext, "Helvetica-Bold", 10)
            dls = lines(q.get("description", ""), "Helvetica-Oblique", 8.3) if q.get("description") else []
            total = 12 * len(qls) + 10.5 * len(dls) + opt_height(q) + 12
            need(total)
            draw_lines(qls, "Helvetica-Bold", 10, INK, 12)
            if dls:
                draw_lines(dls, "Helvetica-Oblique", 8.3, MUT, 10.5)
            state["y"] -= 2

            ft = q["field_type"]
            name = q["id"]
            opts = q.get("options") or []
            common = dict(borderColor=LINE, fillColor=white, textColor=INK,
                          forceBorder=True, borderWidth=0.8)
            if ft == "ja_nein":
                yb = state["y"] - 12
                for i, o in enumerate(["Ja", "Nein"]):
                    xx = LM + 6 + i * 90
                    form.radio(name=name, value=o, selected=False, x=xx, y=yb, size=11,
                               shape="circle", buttonStyle="circle", **common)
                    c.setFont("Helvetica", 9.5)
                    c.setFillColor(INK)
                    c.drawString(xx + 16, yb + 1, o)
                state["y"] = yb - 5
            elif ft in ("auswahl_einfach", "auswahl_mehrfach"):
                for i, o in enumerate(opts):
                    yb = state["y"] - 12
                    if ft == "auswahl_einfach":
                        form.radio(name=name, value=o, selected=False, x=LM + 6, y=yb,
                                   size=11, shape="circle", buttonStyle="circle", **common)
                    else:
                        form.checkbox(name=f"{name}_{i}", x=LM + 6, y=yb, size=11,
                                      buttonStyle="check", **common)
                    c.setFont("Helvetica", 9.5)
                    c.setFillColor(INK)
                    for ln in simpleSplit(o, "Helvetica", 9.5, CW - 30):
                        c.drawString(LM + 24, yb + 1, ln)
                        break
                    state["y"] = yb - 5
            elif ft == "zahl":
                yb = state["y"] - 16
                form.textfield(name=name, x=LM + 6, y=yb, width=150, height=15,
                               fontSize=9, **common)
                state["y"] = yb - 4
            else:
                yb = state["y"] - 24
                form.textfield(name=name, x=LM + 6, y=yb, width=CW - 12, height=22,
                               fontSize=9, **common)
                state["y"] = yb - 4
            state["y"] -= 6

    footer()
    c.showPage()
    c.save()


build_md()
build_html()
build_pdf()
n = sum(len(s["questions"]) for s in SECTIONS)
print(f"OK: {len(SECTIONS)} Abschnitte, {n} Fragen -> fragenkatalog.pdf / .html / .md")
