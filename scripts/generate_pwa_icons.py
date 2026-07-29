"""Generate PWA icon assets for VideoTranscriptAPI (design: docs/designs/pwa.md T3).

Brief (design review): soundwave merged with subtitle lines, flat geometry,
brand gradient background, generous safe-zone padding for the maskable icon.

The script renders three candidates into ``src/web/static/icons/candidates/``
for picking, then produces the final assets from the chosen candidate
(default: candidate 1)::

    uv run python scripts/generate_pwa_icons.py                # candidate 1
    uv run python scripts/generate_pwa_icons.py --candidate 2  # switch later

Final assets (paths are referenced by manifest.webmanifest and the pages):
- icon-192.png / icon-512.png        regular icons
- icon-maskable-512.png              maskable (full-bleed bg, content in safe zone)
- apple-touch-icon.png               180px, opaque (iOS does not support alpha)

Console output is ASCII-only per repo conventions.
"""

import argparse
from pathlib import Path

from PIL import Image, ImageDraw

STATIC_ICONS_DIR = Path(__file__).resolve().parent.parent / "src" / "web" / "static" / "icons"

# Brand gradient: theme_color #4f46e5 -> violet (design spec E2).
BRAND_TOP = (79, 70, 229)     # #4f46e5
BRAND_BOTTOM = (124, 58, 237) # #7c3aed
WHITE = (255, 255, 255)


def _lerp(a: int, b: int, t: float) -> int:
    return round(a + (b - a) * t)


def _vertical_gradient(size: int, top: tuple[int, int, int], bottom: tuple[int, int, int]) -> Image.Image:
    """Create a vertical linear gradient RGB image of ``size`` x ``size``."""
    img = Image.new("RGB", (size, size))
    px = img.load()
    for y in range(size):
        t = y / (size - 1) if size > 1 else 0.0
        color = tuple(_lerp(top[i], bottom[i], t) for i in range(3))
        for x in range(size):
            px[x, y] = color
    return img


def _background(size: int, corner_radius: int) -> Image.Image:
    """Brand gradient background; ``corner_radius=0`` means full-bleed square."""
    img = _vertical_gradient(size, BRAND_TOP, BRAND_BOTTOM).convert("RGBA")
    if corner_radius > 0:
        mask = Image.new("L", (size, size), 0)
        ImageDraw.Draw(mask).rounded_rectangle(
            [0, 0, size - 1, size - 1], radius=corner_radius, fill=255
        )
        img.putalpha(mask)
    return img


def _draw_waveform(draw: ImageDraw.ImageDraw, cx: float, cy: float, scale: float, color=WHITE) -> None:
    """Draw five rounded soundwave bars centered on (cx, cy)."""
    heights = [0.30, 0.58, 0.92, 0.66, 0.40]  # relative to scale
    bar_w = 0.11 * scale
    gap = 0.075 * scale
    total_w = len(heights) * bar_w + (len(heights) - 1) * gap
    x0 = cx - total_w / 2
    for i, h in enumerate(heights):
        bar_h = h * scale
        x = x0 + i * (bar_w + gap)
        draw.rounded_rectangle(
            [x, cy - bar_h / 2, x + bar_w, cy + bar_h / 2],
            radius=bar_w / 2,
            fill=color,
        )


def _draw_subtitle_lines(draw: ImageDraw.ImageDraw, cx: float, top: float, scale: float) -> None:
    """Draw two flat subtitle bars (second one shorter), slightly transparent."""
    line_h = 0.075 * scale
    widths = [0.62 * scale, 0.42 * scale]
    gap = 0.10 * scale
    color = (*WHITE, 190)
    for i, w in enumerate(widths):
        y = top + i * (line_h + gap)
        draw.rounded_rectangle(
            [cx - w / 2, y, cx + w / 2, y + line_h],
            radius=line_h / 2,
            fill=color,
        )


def _fg_candidate_1(img: Image.Image, box: float) -> None:
    """Candidate 1: soundwave + subtitle lines (soundwave merged into captions)."""
    draw = ImageDraw.Draw(img)
    size = img.size[0]
    cx = size / 2
    _draw_waveform(draw, cx, size / 2 - 0.08 * box, 0.62 * box)
    _draw_subtitle_lines(draw, cx, size / 2 + 0.28 * box, 0.62 * box)


def _fg_candidate_2(img: Image.Image, box: float) -> None:
    """Candidate 2: white ring + soundwave only (minimal)."""
    draw = ImageDraw.Draw(img)
    size = img.size[0]
    cx = cy = size / 2
    ring_r = 0.42 * box
    ring_w = 0.055 * box
    draw.ellipse(
        [cx - ring_r, cy - ring_r, cx + ring_r, cy + ring_r],
        outline=WHITE,
        width=max(1, round(ring_w)),
    )
    _draw_waveform(draw, cx, cy, 0.52 * box)


def _fg_candidate_3(img: Image.Image, box: float) -> None:
    """Candidate 3: play triangle built from soundwave bars + one subtitle line."""
    draw = ImageDraw.Draw(img)
    size = img.size[0]
    cx = size / 2
    heights = [0.34, 0.62, 0.90]
    bar_w = 0.14 * box
    gap = 0.09 * box
    total_w = len(heights) * bar_w + (len(heights) - 1) * gap
    x0 = cx - total_w / 2
    cy = size / 2 - 0.06 * box
    scale = 0.58 * box
    for i, h in enumerate(heights):
        bar_h = h * scale
        x = x0 + i * (bar_w + gap)
        draw.rounded_rectangle(
            [x, cy - bar_h / 2, x + bar_w, cy + bar_h / 2],
            radius=bar_w / 2,
            fill=WHITE,
        )
    _draw_subtitle_lines(draw, cx, size / 2 + 0.30 * box, 0.60 * box)


_CANDIDATES = {1: _fg_candidate_1, 2: _fg_candidate_2, 3: _fg_candidate_3}


def _render(candidate: int, size: int, *, maskable: bool = False) -> Image.Image:
    """Render one icon.

    Regular icons: rounded-square gradient, foreground in an 80% box.
    Maskable icons: full-bleed gradient (launchers mask the shape), foreground
    shrunk into the 66% safe zone.
    """
    if maskable:
        img = _background(size, corner_radius=0)
        _CANDIDATES[candidate](img, size * 0.66)
    else:
        img = _background(size, corner_radius=round(size * 0.22))
        _CANDIDATES[candidate](img, size * 0.80)
    return img


def generate_icons(out_dir: Path = STATIC_ICONS_DIR, candidate: int = 1) -> list[Path]:
    """Render the three candidates and write final assets for ``candidate``.

    Args:
        out_dir: Target directory for icon assets (candidates go to ``out_dir/candidates``).
        candidate: Chosen candidate number (1-3) for the final assets.

    Returns:
        List of all written file paths.
    """
    if candidate not in _CANDIDATES:
        raise ValueError(f"unknown candidate: {candidate}")
    out_dir.mkdir(parents=True, exist_ok=True)
    candidates_dir = out_dir / "candidates"
    candidates_dir.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []

    for n in sorted(_CANDIDATES):
        path = candidates_dir / f"candidate-{n}.png"
        _render(n, 512).save(path, "PNG")
        written.append(path)
        print(f"wrote {path}")

    finals = {
        "icon-192.png": _render(candidate, 192),
        "icon-512.png": _render(candidate, 512),
        "icon-maskable-512.png": _render(candidate, 512, maskable=True),
        # apple-touch-icon: opaque full-bleed (iOS applies its own mask, no alpha)
        "apple-touch-icon.png": _render(candidate, 180, maskable=True).convert("RGB"),
    }
    for name, img in finals.items():
        path = out_dir / name
        img.save(path, "PNG")
        written.append(path)
        print(f"wrote {path}")

    return written


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate PWA icon assets.")
    parser.add_argument(
        "--candidate",
        type=int,
        default=1,
        choices=sorted(_CANDIDATES),
        help="Which candidate to use for the final assets (default: 1).",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=STATIC_ICONS_DIR,
        help="Output directory (default: src/web/static/icons).",
    )
    args = parser.parse_args()
    generate_icons(out_dir=args.out, candidate=args.candidate)
    print(f"done (final assets from candidate {args.candidate})")


if __name__ == "__main__":
    main()
