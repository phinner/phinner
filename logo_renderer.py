#!/usr/bin/env python3
"""This is a script describing how to render my logo.
Basically the debian swirl within a rounded hexagon.
I lost the original files so I got codex and claude to reverse engineer it using the inkscape source code.
Resulting in this very handy script.
AI is so peak.
"""

"""Draw the logo. It is only three filled shapes, painted back to front:

1. a rounded hexagon in the main colour,
2. a slightly smaller one in the fill colour -- the sliver of the first shape
   still showing around it is the ring,
3. a swirl in the main colour, cut off by a third, smaller hexagon.

There are no strokes and no outlines anywhere; every edge you see is one shape
ending or another shape covering it.

Everything is drawn on a unit square: positions and lengths in the knobs below
are fractions of the canvas, and --size only picks the export resolution.

    python3 render_logo_final_custom.py --svg logo.svg --png logo.png
    python3 render_logo_final_custom.py --size 1024 --color-1 '#ff8800'
"""

import argparse
import math
import shutil
import subprocess
from pathlib import Path
from xml.sax.saxutils import escape

TAU = 2.0 * math.pi

# ---------------------------------------------------------------- the knobs --
# In drawing order: the hexagons first, then the swirl laid over them.

# All three hexagons share this centre. A hexagon is six points on a circle;
# its radius is measured centre to corner.
HEX_CENTER = (0.5, 0.5)
OUTER_RADIUS = 0.41  # the ring's outside edge
INNER_RADIUS = 0.38  # the ring's inside edge; the ring is the difference
CLIP_RADIUS = 0.30   # the swirl is cut to this one

# How much the hexagon sides bow outward. Each side is drawn as a curve whose
# control handles have length ROUNDEDNESS x side length; 0 means straight sides.
ROUNDEDNESS = 0.10

# The swirl's centreline is a circle whose radius keeps growing. Walking a
# parameter t from INNER_HOLE outward:
#
#     angle  = ROTATION + REVOLUTIONS * t turns
#     radius = SPIRAL_RADIUS * t ** EXPANSION
#
# ROTATION spins the whole swirl. EXPANSION sets coil spacing: 1 is even like a
# rolled rope, higher bunches the middle and opens the outside. INNER_HOLE is
# where drawing starts; at t = 0 the spiral would collapse to a point.
SPIRAL_CENTER = (0.47, 0.5)
SPIRAL_RADIUS = 0.32
ROTATION = math.radians(25.0)
REVOLUTIONS = 2.9
EXPANSION = 2
INNER_HOLE = 0.15

# The band's half-width: zero at the centre (a sharp point), growing on a
# straight ramp to this value at t = 1, and past it at the same rate. The
# spiral is deliberately drawn beyond the clip hexagon so that the visible
# swirl ends on the hexagon's edge, never on the band's own end cap.
END_HALF_WIDTH = 0.06

# Level of detail. The band's outline is straight segments, one per sample, so
# this is literally corners per revolution: 100 reads as smooth, 8 is
# octagonal, 4 is a squared-off spiral.
SAMPLES_PER_TURN = 100

# -----------------------------------------------------------------------------


def fmt(value: float) -> str:
    """Six decimals: a thousandth of a pixel even at a 1024 px export."""
    return f"{value:.6f}".rstrip("0").rstrip(".")


def unit(x: float, y: float) -> tuple[float, float]:
    length = math.hypot(x, y)
    return x / length, y / length


def hex_path(radius: float) -> str:
    """One rounded hexagon as an SVG path.

    Six corners, evenly spaced on a circle, starting straight up. Each side is
    a cubic curve; the handle at each corner points along the circle (the same
    direction as the line from the previous corner to the next one) and has
    length ROUNDEDNESS x side length, which is what makes the sides bow out
    while the corners stay put.
    """
    cx, cy = HEX_CENTER
    corners = [
        (cx + radius * math.cos(a), cy + radius * math.sin(a))
        for a in (-math.pi / 2 + i * TAU / 6 for i in range(6))
    ]

    commands = [f"M {fmt(corners[0][0])},{fmt(corners[0][1])}"]
    for i, start in enumerate(corners):
        prev, end, after = corners[i - 1], corners[(i + 1) % 6], corners[(i + 2) % 6]
        handle = ROUNDEDNESS * math.dist(start, end)
        t1 = unit(end[0] - prev[0], end[1] - prev[1])
        t2 = unit(after[0] - start[0], after[1] - start[1])
        commands.append(
            "C "
            f"{fmt(start[0] + handle * t1[0])},{fmt(start[1] + handle * t1[1])} "
            f"{fmt(end[0] - handle * t2[0])},{fmt(end[1] - handle * t2[1])} "
            f"{fmt(end[0])},{fmt(end[1])}"
        )
    commands.append("Z")
    return " ".join(commands)


def half_width(t: float) -> float:
    return END_HALF_WIDTH * (t - INNER_HOLE) / (1.0 - INNER_HOLE)


def runout_end_t() -> float:
    """How far past t = 1 the spiral must run to fully clear the clip hexagon.

    Every point of the clip is within CLIP_RADIUS of the hexagon centre, and
    the band's nearest point at parameter t is at least

        SPIRAL_RADIUS * t ** EXPANSION - centre offset - half_width(t)

    from that centre. Once that exceeds CLIP_RADIUS the whole cross-section is
    outside the clip, whatever angle it happens to cross at.
    """
    target = CLIP_RADIUS + math.dist(SPIRAL_CENTER, HEX_CENTER)
    t = 1.0
    while t < 2.0 and SPIRAL_RADIUS * t**EXPANSION - half_width(t) < target:
        t += 0.001
    return t


def swirl_path(end_t: float) -> str:
    """The swirl as one closed filled outline.

    Walk the spiral's centreline; at every sample step half_width to each side,
    perpendicular to the direction of travel. All the left-side points forward,
    then all the right-side points backward, close the path: a ribbon. At the
    start the width is zero, so the ribbon begins in a sharp point.
    """
    samples = max(3, round(SAMPLES_PER_TURN * REVOLUTIONS * (end_t - INNER_HOLE)))
    cx, cy = SPIRAL_CENTER
    left, right = [], []

    for i in range(samples + 1):
        t = INNER_HOLE + (end_t - INNER_HOLE) * i / samples
        theta = ROTATION + TAU * REVOLUTIONS * t
        radius = t**EXPANSION

        x = cx + SPIRAL_RADIUS * radius * math.cos(theta)
        y = cy + SPIRAL_RADIUS * radius * math.sin(theta)

        # Exact tangent of (radius growing, angle turning), rotated a quarter
        # turn to point sideways.
        dr = EXPANSION * t ** (EXPANSION - 1)
        dx = dr * math.cos(theta) - radius * TAU * REVOLUTIONS * math.sin(theta)
        dy = dr * math.sin(theta) + radius * TAU * REVOLUTIONS * math.cos(theta)
        nx, ny = unit(-dy, dx)

        w = half_width(t)
        left.append((x + nx * w, y + ny * w))
        right.append((x - nx * w, y - ny * w))

    outline = left + right[::-1]
    return (
        f"M {fmt(outline[0][0])},{fmt(outline[0][1])} "
        + " ".join(f"L {fmt(x)},{fmt(y)}" for x, y in outline[1:])
        + " Z"
    )


def svg_document(size: int, color_1: str, color_2: str) -> str:
    c1 = escape(color_1, {'"': "&quot;"})
    c2 = escape(color_2, {'"': "&quot;"})
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg"
     width="{size}" height="{size}" viewBox="0 0 1 1">
  <title>Hexagonal swirl logo</title>
  <defs>
    <clipPath id="swirl-clip" clipPathUnits="userSpaceOnUse">
      <path d="{hex_path(CLIP_RADIUS)}"/>
    </clipPath>
  </defs>
  <path id="outer-hex" d="{hex_path(OUTER_RADIUS)}" fill="{c1}"/>
  <path id="inner-hex" d="{hex_path(INNER_RADIUS)}" fill="{c2}"/>
  <path id="swirl" d="{swirl_path(runout_end_t())}" fill="{c1}" clip-path="url(#swirl-clip)"/>
</svg>
"""


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--svg", type=Path, default=Path("logo-custom.svg"))
    parser.add_argument("--png", type=Path, help="also export a PNG using Inkscape")
    parser.add_argument("--size", type=int, default=400, help="output width and height")
    parser.add_argument("--color-1", default="#00ffff", help="ring and swirl")
    parser.add_argument("--color-2", default="#000000", help="fill between them")
    args = parser.parse_args()

    if args.size <= 0:
        raise SystemExit("--size must be a positive integer")

    args.svg.parent.mkdir(parents=True, exist_ok=True)
    args.svg.write_text(
        svg_document(args.size, args.color_1, args.color_2), encoding="utf-8"
    )
    print(f"wrote {args.svg}")

    if args.png:
        inkscape = shutil.which("inkscape")
        if not inkscape:
            raise SystemExit("PNG export requested, but 'inkscape' is not on PATH")
        args.png.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [
                inkscape,
                str(args.svg.resolve()),
                f"--export-filename={args.png.resolve()}",
                f"--export-width={args.size}",
                f"--export-height={args.size}",
                "--export-background-opacity=0",
            ],
            check=True,
        )
        print(f"wrote {args.png}")


if __name__ == "__main__":
    main()
