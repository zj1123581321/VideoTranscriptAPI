"""Regenerate the subset fonts used by tests/og_card.

Source: Noto Sans SC variable font (OFL), downloaded from google/fonts:
  https://github.com/google/fonts/raw/main/ofl/notosanssc/NotoSansSC%5Bwght%5D.ttf
License: tests/og_card/fonts/OFL.txt (SIL Open Font License 1.1).

Glyph coverage is derived from every non-ASCII character that appears in
tests/og_card/*.py and in the renderer source (its own text literals, e.g.
the "AI 总结" footer label), plus a fixed ASCII printable set, so any new
Chinese text added to the tests or the renderer must be followed by a rerun
of this script:

  uv run --with fonttools python tests/og_card/fonts/build_subsets.py \
      --source /path/to/NotoSansSC-VF.ttf

Outputs: tests/og_card/fonts/NotoSansSC-Regular-subset.ttf (wght=400) and
NotoSansSC-Bold-subset.ttf (wght=700), each kept under 300KB.
"""

from __future__ import annotations

import argparse
import string
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont

TESTS_DIR = Path(__file__).resolve().parent.parent
RENDERER_SRC = (
    Path(__file__).resolve().parents[3]
    / "src" / "video_transcript_api" / "utils" / "rendering" / "og_card.py"
)
OUTPUT_DIR = Path(__file__).resolve().parent


def collect_characters() -> str:
    chars = set(string.printable)
    scan_paths = [*sorted(TESTS_DIR.glob("*.py")), RENDERER_SRC]
    for path in scan_paths:
        chars.update(path.read_text(encoding="utf-8"))
    # Layout constants referenced by the renderer but not spelled out in tests.
    chars.update("…·")
    chars.discard("\n")
    chars.discard("\r")
    return "".join(sorted(chars))


def build(source: Path, weight: int, out_name: str) -> None:
    font = TTFont(str(source))
    instantiateVariableFont(font, {"wght": weight}, inplace=True)
    options = subset.Options()
    options.flavor = None
    options.desubroutinize = True
    options.drop_tables += ["FFTM"]
    subsetter = subset.Subsetter(options)
    subsetter.populate(text=collect_characters())
    subsetter.subset(font)
    out_path = OUTPUT_DIR / out_name
    font.save(str(out_path))
    size_kb = out_path.stat().st_size / 1024
    print(f"{out_path.name}: {size_kb:.0f} KB ({weight=})")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    args = parser.parse_args()
    build(args.source, 400, "NotoSansSC-Regular-subset.ttf")
    build(args.source, 700, "NotoSansSC-Bold-subset.ttf")


if __name__ == "__main__":
    main()
