"""gen_favicon.py — generate the cockpit's favicon assets from one set of
hand-picked geometry parameters, so the SVG (served as <link rel="icon">)
and the ICO (served at the well-known /favicon.ico path browsers fetch
regardless of markup) never drift apart.

Self-drawn on purpose (project tabu: no CDN, no external material) — a
signal/broadcast glyph (a node with two radiating arcs), fitting a LoRaWAN
gateway cockpit. An opaque rounded-square background in the app's light-
theme accent blue keeps it legible on both light and dark browser tab
bars — a favicon has no access to the page's own dark-mode toggle, so it
carries its own fixed, high-contrast background rather than relying on the
browser's chrome color.

Run manually when the icon design changes:
    python scripts/gen_favicon.py
Writes cockpit/app/static/favicon.svg and cockpit/app/static/favicon.ico.
Requires Pillow (already a cockpit runtime dependency, see requirements.txt).
"""
import math
import os

from PIL import Image, ImageDraw

# --- Shared geometry (one set of numbers, two renderers) -------------------
SIZE = 32
BG = "#2454c7"       # cockpit light-theme --accent
FG = (255, 255, 255)  # white glyph, for contrast against BG on any tab bar
CX, CY = 16, 22.5     # node dot center
DOT_R = 2.6
ARC_RADII = (6.2, 10.6)   # inner/outer signal arcs
ARC_START_DEG, ARC_END_DEG = 200, 340  # PIL convention: 0=east, clockwise
ARC_STROKE = 2.4
FG_HEX = "#%02x%02x%02x" % FG


def _arc_endpoints(r: float, start_deg: float, end_deg: float):
    pts = []
    for deg in (start_deg, end_deg):
        rad = math.radians(deg)
        pts.append((CX + r * math.cos(rad), CY + r * math.sin(rad)))
    return pts


def write_svg(path: str) -> None:
    arcs_svg = []
    for r in ARC_RADII:
        (x1, y1), (x2, y2) = _arc_endpoints(r, ARC_START_DEG, ARC_END_DEG)
        arcs_svg.append(
            f'<path d="M {x1:.2f} {y1:.2f} A {r} {r} 0 0 1 {x2:.2f} {y2:.2f}" '
            f'fill="none" stroke="{FG_HEX}" stroke-width="{ARC_STROKE}" '
            'stroke-linecap="round"/>'
        )
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {SIZE} {SIZE}">
  <rect width="{SIZE}" height="{SIZE}" rx="7" fill="{BG}"/>
  <circle cx="{CX}" cy="{CY}" r="{DOT_R}" fill="{FG_HEX}"/>
  {chr(10).join(arcs_svg)}
</svg>
'''
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(svg)


def write_ico(path: str) -> None:
    # Draw at 4x and downsample per target size for anti-aliased edges —
    # PIL's ImageDraw has no native supersampling.
    scale = 4
    sizes = (16, 24, 32, 48)
    frames = []
    for size in sizes:
        canvas_size = size * scale
        k = canvas_size / SIZE
        im = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.rounded_rectangle((0, 0, canvas_size - 1, canvas_size - 1), radius=7 * k, fill=BG)
        d.ellipse(
            (
                (CX - DOT_R) * k, (CY - DOT_R) * k,
                (CX + DOT_R) * k, (CY + DOT_R) * k,
            ),
            fill=FG,
        )
        for r in ARC_RADII:
            bbox = (
                (CX - r) * k, (CY - r) * k,
                (CX + r) * k, (CY + r) * k,
            )
            d.arc(bbox, ARC_START_DEG, ARC_END_DEG, fill=FG, width=max(1, round(ARC_STROKE * k)))
        im = im.resize((size, size), Image.LANCZOS)
        frames.append(im)
    # Pillow's ICO encoder filters requested `sizes` against the base
    # image's OWN size (it will not upscale) — the base image must be the
    # LARGEST frame, with the smaller ones passed in via append_images.
    frames[-1].save(
        path,
        format="ICO",
        sizes=[(f.width, f.height) for f in frames],
        append_images=frames[:-1],
    )


if __name__ == "__main__":
    static_dir = os.path.join(os.path.dirname(__file__), "..", "cockpit", "app", "static")
    static_dir = os.path.abspath(static_dir)
    write_svg(os.path.join(static_dir, "favicon.svg"))
    write_ico(os.path.join(static_dir, "favicon.ico"))
    print("Wrote", os.path.join(static_dir, "favicon.svg"))
    print("Wrote", os.path.join(static_dir, "favicon.ico"))
