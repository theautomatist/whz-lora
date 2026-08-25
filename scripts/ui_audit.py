#!/usr/bin/env python3
"""Operate the cockpit in a real browser and report what a code review cannot see.

Why this exists: the cockpit redesign was first analysed by reading code and
querying the database. That found plenty, but it missed defects that only
appear once the interface is rendered with real data — an unbounded 8885 px
list, and 34 px of horizontal overflow on a 390 px phone viewport. Both are
plainly visible after one look and invisible in the source.

So looking is now a repeatable step, not a one-off.

What it measures, per view:
  * horizontal overflow (fatal on a phone) and which elements cause it
  * page height in screenfuls
  * every list-like container: item count, rendered height, whether it is
    scroll-contained, and whether it offers sort / filter / search
  * screenshots at phone and desktop widths

Usage:
    python scripts/ui_audit.py --url http://localhost:8000 \
        --user admin --password secret --out _backup/ui-audit

Requires `playwright` and a browser. It uses the installed Edge by default
(`--channel msedge`), so no separate browser download is needed on Windows.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

# Containers worth measuring. A list is "interesting" when its length is
# driven by data rather than by layout.
LIST_CONTAINERS = [
    "rf-vendors", "rf-devices", "rf-networks", "rf-frame-log",
    "rf-sf-dist", "rf-rssi-dist", "rf-mtype-breakdown", "rf-timeline",
    "dev-list-body", "history-list-body", "events-log-body",
    "card-dashboard", "map-unplaced-list",
]

# The view switch buttons, in the order a person meets them.
VIEWS = [
    ("live", "#vsw-live"),
    ("history", "#vsw-history"),
    ("map", "#vsw-map"),
    ("events", "#vsw-events"),
]

VIEWPORTS = {"phone": (390, 844), "desktop": (1440, 900)}

_JS_OVERFLOW = """() => {
  const vw = document.documentElement.clientWidth;
  const out = {viewport: vw, scrollWidth: document.documentElement.scrollWidth,
               pageHeight: document.body.scrollHeight, culprits: []};
  const seen = new Set();
  document.querySelectorAll('*').forEach(el => {
    const r = el.getBoundingClientRect();
    if (r.width > 0 && r.right > vw + 1) {
      // Only report an element when its parent is not already over the edge —
      // otherwise one bad element produces hundreds of inherited reports.
      const p = el.parentElement;
      if (p && p.getBoundingClientRect().right > vw + 1) return;
      const key = el.tagName + '#' + el.id + '.' + el.className;
      if (seen.has(key)) return;
      seen.add(key);
      out.culprits.push({
        tag: el.tagName.toLowerCase(), id: el.id || null,
        cls: (typeof el.className === 'string' ? el.className : '').slice(0, 48) || null,
        right: Math.round(r.right), width: Math.round(r.width),
      });
    }
  });
  return out;
}"""

_JS_LISTS = """(ids) => ids.map(id => {
  const el = document.getElementById(id);
  if (!el) return {id, present: false};
  const cs = getComputedStyle(el);
  const contained = el.scrollHeight > el.clientHeight + 2 &&
                    (cs.overflowY === 'auto' || cs.overflowY === 'scroll');
  const bounded = cs.maxHeight !== 'none' ||
                  (cs.overflowY === 'auto' || cs.overflowY === 'scroll');
  return {
    id, present: true, visible: el.offsetParent !== null || cs.position === 'fixed',
    items: el.children.length,
    clientH: el.clientHeight, scrollH: el.scrollHeight,
    overflowY: cs.overflowY, maxHeight: cs.maxHeight,
    contained, bounded,
  };
})"""

# Sort / filter / search controls, located by what they actually are rather
# than by naming convention, so a renamed control is still found.
_JS_CONTROLS = """() => {
  const q = sel => Array.from(document.querySelectorAll(sel))
    .filter(e => e.offsetParent !== null)
    .map(e => e.id || e.getAttribute('aria-label') || e.className || e.tagName.toLowerCase());
  return {
    search: q('input[type=search]'),
    selects: q('select'),
    textFilters: q('input[type=text][data-filter], input[placeholder*="ilter"], input[placeholder*="uch"]'),
    chips: q('[class*=chip]'),
  };
}"""


def audit(url: str, user: str, password: str, out_dir: str, channel: str) -> dict:
    from playwright.sync_api import sync_playwright

    os.makedirs(out_dir, exist_ok=True)
    report: dict = {"url": url, "viewports": {}}

    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel=channel, headless=True)
        try:
            for vp_name, (w, h) in VIEWPORTS.items():
                ctx = browser.new_context(
                    http_credentials={"username": user, "password": password},
                    viewport={"width": w, "height": h},
                )
                page = ctx.new_page()
                page.goto(url, wait_until="networkidle")
                page.wait_for_timeout(4000)  # SSE connect + first data render

                vp_report: dict = {"views": {}}
                for view_name, switch in VIEWS:
                    btn = page.query_selector(switch)
                    if btn:
                        btn.click()
                        page.wait_for_timeout(2500)
                    # Expand every <details> so collapsed content is measured too;
                    # a defect hidden behind a disclosure triangle is still a defect.
                    page.evaluate("() => document.querySelectorAll('details').forEach(d => d.open = true)")
                    page.wait_for_timeout(1200)

                    overflow = page.evaluate(_JS_OVERFLOW)
                    lists = [l for l in page.evaluate(_JS_LISTS, LIST_CONTAINERS)
                             if l.get("present") and l.get("visible")]
                    controls = page.evaluate(_JS_CONTROLS)

                    shot = os.path.join(out_dir, f"{vp_name}-{view_name}.png")
                    page.screenshot(path=shot, full_page=True)

                    vp_report["views"][view_name] = {
                        "overflow": overflow, "lists": lists,
                        "controls": controls, "screenshot": shot,
                    }
                report["viewports"][vp_name] = vp_report
                ctx.close()
        finally:
            browser.close()
    return report


def _containment(lst: dict, viewport_h: int) -> str:
    """Judge a list's height behaviour.

    The subtle case this exists for: a container with no max-height simply
    grows to fit its rows, so scrollHeight == clientHeight and a naive check
    reports "fits, nothing to scroll". That is precisely the defect — an
    8885 px list reads as healthy. So height is judged against the viewport,
    not against the element's own (self-fulfilling) box.
    """
    if lst["contained"]:
        return "scrolls in place"
    if lst["bounded"]:
        return "capped"
    if lst["scrollH"] > viewport_h:
        return f"**UNBOUNDED — {lst['scrollH'] / viewport_h:.1f} screenfuls**"
    return "fits"


def to_markdown(report: dict) -> str:
    lines = ["# Cockpit UI audit", "", f"Target: `{report['url']}`", ""]
    for vp_name, vp in report["viewports"].items():
        lines += [f"## Viewport: {vp_name}", ""]
        for view_name, v in vp["views"].items():
            o = v["overflow"]
            over = o["scrollWidth"] - o["viewport"]
            screens = o["pageHeight"] / (844 if vp_name == "phone" else 900)
            lines += [
                f"### View: {view_name}", "",
                f"- Page height: **{o['pageHeight']} px** ({screens:.1f} screenfuls)",
                f"- Horizontal overflow: **{over} px**"
                + (" — content is cut off sideways" if over > 1 else " (none)"),
            ]
            if over > 1 and o["culprits"]:
                lines.append("- Outermost elements past the right edge:")
                for c in o["culprits"][:6]:
                    ident = f"#{c['id']}" if c["id"] else (f".{c['cls']}" if c["cls"] else c["tag"])
                    lines.append(f"    - `<{c['tag']} {ident}>` width {c['width']}, right edge {c['right']}")
            if v["lists"]:
                lines += ["", "| List | Items | Height | Containment | max-height |",
                          "|---|---:|---:|---|---|"]
                vp_h = 844 if vp_name == "phone" else 900
                for l in v["lists"]:
                    lines.append(f"| `#{l['id']}` | {l['items']} | {l['scrollH']} px |"
                                 f" {_containment(l, vp_h)} | {l['maxHeight']} |")
            c = v["controls"]
            lines += ["", f"- Search inputs: **{len(c['search'])}**"
                      f" · selects: {len(c['selects'])} · chips: {len(c['chips'])}", ""]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", default="http://localhost:8000")
    ap.add_argument("--user", default=os.environ.get("COCKPIT_USER", "admin"))
    ap.add_argument("--password", default=os.environ.get("COCKPIT_PASSWORD", "change-me"))
    ap.add_argument("--out", default="_backup/ui-audit")
    ap.add_argument("--channel", default="msedge",
                    help="Playwright browser channel (msedge, chrome, or '' for bundled chromium)")
    args = ap.parse_args()

    report = audit(args.url, args.user, args.password, args.out, args.channel or None)
    md = to_markdown(report)
    md_path = os.path.join(args.out, "report.md")
    with open(md_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(md)
    with open(os.path.join(args.out, "report.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(report, f, indent=2)
    print(md)
    print(f"\nWritten to {md_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
