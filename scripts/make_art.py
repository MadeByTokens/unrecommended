"""Draw the project's artwork: site/logo.svg, site/favicon.svg, docs/banner.svg.

Usage: python scripts/make_art.py [repo root, default "."]

docs/banner.png and site/apple-touch-icon.png are renderings of these SVGs
(the banner at 2560x800, the favicon at 180x180 with square corners); make
them with any browser or SVG renderer after changing the drawings.
"""

import math
import sys
from pathlib import Path

root = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
PAPER, INK, BRICK, GREY = "#f6f3ec", "#1f1d1a", "#b4462b", "#6b655c"
SERIF = "'Iowan Old Style','Palatino Linotype',Palatino,Georgia,serif"
SANS = "system-ui,-apple-system,'Segoe UI',Roboto,'Helvetica Neue',Arial,sans-serif"


def tv_mark(ink="var(--ink)", tag=True):
    """The TV in a 64x64 box: sleepy kissy face, do-not-disturb tag."""

    def st(w=2.6, color=None):
        return f'stroke="{color or ink}" stroke-width="{w}" stroke-linecap="round" stroke-linejoin="round"'

    s = st()
    parts = [
        # antennae + base
        f'<path d="M30 20 L21 7 M30 20 L39 8" fill="none" {s}/>',
        f'<circle cx="21" cy="7" r="1.8" fill="{ink}"/>',
        # legs
        f'<path d="M16 54 L13 59.5 M45 54 L48 59.5" fill="none" {s}/>',
        # body
        f'<rect x="7" y="20" width="47" height="35" rx="7" fill="{BRICK}" {s}/>',
        f'<path d="M26 20 a4 4 0 0 1 8 0" fill="{ink}"/>',
        # screen
        f'<rect x="12" y="25" width="30" height="25" rx="5.5" fill="{PAPER}" {s}/>',
        # knobs
        f'<circle cx="48" cy="32" r="2.2" fill="{PAPER}" stroke="{ink}" stroke-width="1.8"/>',
        f'<circle cx="48" cy="40" r="2.2" fill="{PAPER}" stroke="{ink}" stroke-width="1.8"/>',
        # face: closed eyes, little kiss
        f'<path d="M17.5 34 q2.7 3 5.4 0 M30.5 34 q2.7 3 5.4 0" fill="none" {st(2.2, INK)}/>',
        f'<path d="M26 40.2 c2.3 0 2.3 1.9 0 1.9 c2.3 0 2.3 1.9 0 1.9" fill="none" {st(1.9, INK)}/>',
    ]
    if tag:
        parts += [
            f'<path d="M39 8 C44 8 47 10 47.5 13.5" fill="none" stroke="{ink}" stroke-width="1.6"/>',
            (
                f'<g transform="rotate(16 47.5 13.5)">'
                f'<rect x="42.5" y="12" width="10" height="16" rx="2.2" fill="{BRICK}" {st(2)}/>'
                f'<circle cx="47.5" cy="15" r="1.2" fill="{PAPER}"/>'
                f'<circle cx="47.5" cy="22" r="3" fill="none" stroke="{PAPER}" stroke-width="1.5"/>'
                f'<path d="M45.4 24.1 L49.6 19.9" stroke="{PAPER}" stroke-width="1.5" stroke-linecap="round"/>'
                f"</g>"
            ),
        ]
    return "\n  ".join(parts)


THEME = f"""<style>
    :root {{ --ink: {INK}; }}
    @media (prefers-color-scheme: dark) {{ :root {{ --ink: #ece7de; }} }}
  </style>"""

# ---------------------------------------------------------------- logo
logo = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="4 3 56 58" role="img" aria-label="unrecommended logo">
  {THEME}
  {tv_mark()}
</svg>
"""

# ---------------------------------------------------------------- favicon
# Simplified so it still reads at 16 px: no tag, no knobs, no legs.
favicon = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">
  <rect width="32" height="32" rx="7" fill="{BRICK}"/>
  <g fill="none" stroke="{PAPER}" stroke-linecap="round" stroke-linejoin="round">
    <path d="M16 11 L11.5 5 M16 11 L20.5 5" stroke-width="2"/>
    <rect x="5" y="11" width="22" height="16" rx="3.5" stroke-width="2.4"/>
    <path d="M9.6 18 q1.9 2.2 3.8 0 M18.6 18 q1.9 2.2 3.8 0" stroke-width="1.9"/>
  </g>
</svg>
"""

# ---------------------------------------------------------------- banner
W, H = 1280, 400


def bubble(x, y, w, h, angle, lines, fill="#fffdf8", color=INK, size=19):
    tx = "".join(
        f'<tspan x="{x + w / 2}" dy="{0 if i == 0 else size * 1.15}">{t}</tspan>' for i, t in enumerate(lines)
    )
    ty = y + h / 2 - (len(lines) - 1) * size * 0.575 + size * 0.36
    tail = f"M{x + 22} {y + h - 1} l-8 16 l22 -15"
    return (
        f'<g transform="rotate({angle} {x + w / 2} {y + h / 2})">'
        f'<path d="{tail}" fill="{fill}" stroke="{INK}" stroke-width="2.6" stroke-linejoin="round"/>'
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="14" fill="{fill}" stroke="{INK}" stroke-width="2.6"/>'
        f'<rect x="{x + 14}" y="{y + h - 3}" width="26" height="5" fill="{fill}"/>'
        f'<text x="{x + w / 2}" y="{ty}" text-anchor="middle" font-family="{SANS}" '
        f'font-weight="800" font-size="{size}" fill="{color}" letter-spacing="0.5">{tx}</text></g>'
    )


def arrow(x1, y1, x2, y2, color, width=7):
    a = math.atan2(y2 - y1, x2 - x1)
    hx = [x2 - 18 * math.cos(a - 0.55), x2 - 18 * math.cos(a + 0.55)]
    hy = [y2 - 18 * math.sin(a - 0.55), y2 - 18 * math.sin(a + 0.55)]
    mx, my = (x1 + x2) / 2 + 18 * math.sin(a), (y1 + y2) / 2 - 18 * math.cos(a)
    return (
        f'<path d="M{x1} {y1} Q{mx:.1f} {my:.1f} {x2} {y2}" fill="none" stroke="{color}" '
        f'stroke-width="{width}" stroke-linecap="round"/>'
        f'<path d="M{hx[0]:.1f} {hy[0]:.1f} L{x2} {y2} L{hx[1]:.1f} {hy[1]:.1f}" fill="none" '
        f'stroke="{color}" stroke-width="{width}" stroke-linecap="round" stroke-linejoin="round"/>'
    )


chair = f"""
  <!-- armchair -->
  <g stroke="{INK}" stroke-width="3.2" stroke-linejoin="round">
    <rect x="808" y="168" width="196" height="150" rx="34" fill="#d8cfbe"/>
    <rect x="826" y="262" width="160" height="56" rx="14" fill="#e6dfd1"/>
    <rect x="786" y="232" width="52" height="98" rx="22" fill="#e6dfd1"/>
    <rect x="974" y="232" width="52" height="98" rx="22" fill="#e6dfd1"/>
    <path d="M806 330 l-6 22 M1006 330 l6 22" stroke-linecap="round" fill="none"/>
  </g>
  <!-- the TV, relaxing -->
  <g transform="translate(828 107) scale(2.6)">
    {tv_mark(INK)}
  </g>
  <!-- headphones -->
  <g fill="none" stroke="{INK}" stroke-linecap="round">
    <path d="M842 200 C842 112 976 112 976 200" stroke-width="7"/>
  </g>
  <rect x="830" y="184" width="22" height="48" rx="9" fill="{INK}"/>
  <rect x="966" y="184" width="22" height="48" rx="9" fill="{INK}"/>
  <!-- tea on the armrest -->
  <g stroke="{INK}" stroke-width="3" stroke-linejoin="round" stroke-linecap="round">
    <path d="M792 206 h34 v14 a17 17 0 0 1 -34 0 z" fill="#fffdf8"/>
    <path d="M826 212 a8 8 0 0 1 0 15" fill="none"/>
    <path d="M800 196 q-6 -9 0 -18 t0 -18 M814 196 q-6 -9 0 -18 t0 -18" fill="none" stroke="{GREY}" stroke-width="2.4"/>
  </g>
  <!-- broom, sweeping -->
  <g stroke="{INK}" stroke-linecap="round" stroke-linejoin="round">
    <path d="M992 300 L1062 360" stroke-width="7" stroke="#8a5a36"/>
    <path d="M1052 344 l40 -14 l28 44 l-48 14 z" fill="#d9a441" stroke-width="3"/>
    <path d="M1078 342 l16 34 M1090 337 l18 34 M1068 348 l14 33" stroke-width="2" fill="none"/>
    <path d="M1124 380 q14 -6 22 -18 M1136 388 q16 -4 26 -14" stroke="{GREY}" stroke-width="3" fill="none"/>
  </g>
"""

noise = "".join(
    [
        arrow(1070, 300, 1150, 238, BRICK),
        arrow(1110, 200, 1206, 138, GREY, 6),
        arrow(1160, 300, 1262, 262, INK, 6),
        arrow(1050, 160, 1120, 70, BRICK, 6),
        bubble(1046, 96, 190, 64, -8, ["YOU MAY", "ALSO LIKE!!"], size=18),
        bubble(1128, 172, 132, 70, 9, ["WAIT, ONE", "MORE!"], size=17),
        bubble(1046, 256, 158, 46, -4, ["TRENDING NOW"], fill=BRICK, color="#fff8f0", size=17),
        bubble(1130, 322, 140, 46, 6, ["AUTOPLAY IN 3…"], size=15),
        f'<path d="M1240 40 l6 16 l16 6 l-16 6 l-6 16 l-6 -16 l-16 -6 l16 -6 z" fill="{BRICK}"/>',
        f'<text x="1020" y="70" font-family="{SANS}" font-weight="900" font-size="40" fill="{INK}" transform="rotate(-12 1020 70)">!</text>',
        f'<text x="1266" y="120" font-family="{SANS}" font-weight="900" font-size="34" fill="{BRICK}" transform="rotate(14 1266 120)">!</text>',
    ]
)

banner = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img"
  aria-label="unrecommended: your own YouTube, without the algorithm">
  <rect width="{W}" height="{H}" fill="{PAPER}"/>
  <text x="72" y="190" font-family="{SERIF}" font-weight="700" font-size="74" fill="{INK}"
    letter-spacing="-0.5"><tspan fill="{BRICK}">un</tspan>recommended</text>
  <text font-family="{SANS}" font-size="31" fill="{INK}">
    <tspan x="76" y="246">Your own YouTube,</tspan>
    <tspan x="76" y="286">without the algorithm.</tspan>
  </text>
  <path d="M76 326 h120" stroke="{BRICK}" stroke-width="5" stroke-linecap="round"/>
  {chair}
  {noise}
</svg>
"""

(root / "site" / "logo.svg").write_text(logo)
(root / "site" / "favicon.svg").write_text(favicon)
(root / "docs" / "banner.svg").write_text(banner)
print("ok")
