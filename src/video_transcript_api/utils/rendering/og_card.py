"""OG share-card rendering: llm_share_card.json -> 1200x630 PNG.

Contract (written by the LLM share-card pipeline, read here):
  {"version": 1, "headline": str, "points": [str, ...] (1..3),
   "generated_at": "ISO8601"}

A cache directory without a contract-valid llm_share_card.json has no card:
load_share_card returns None and the /og route must answer 404. There is no
fallback card.
"""

from __future__ import annotations

import json
import os
import tempfile
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from PIL import Image, ImageDraw, ImageFont

from ..logging import setup_logger

logger = setup_logger("og_card")

CARD_FILENAME = "llm_share_card.json"
PNG_FILENAME = "og_card.png"

# Debian fonts-noto-cjk defaults. Both are .ttc collections whose face 0 is
# the JP variant; _load_font picks the SC face when available.
DEFAULT_FONT_PATH = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
DEFAULT_FONT_BOLD_PATH = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"

WIDTH = 1200
HEIGHT = 630
MARGIN = 80
CONTENT_WIDTH = WIDTH - 2 * MARGIN

BG_COLOR = "#15151F"
ACCENT_COLOR = "#667eea"
HEADER_COLOR = "#8B93A7"
TITLE_COLOR = "#F5F6FA"
POINT_COLOR = "#C9CEE0"
FOOTER_COLOR = "#6E7691"

HEADER_FONT_SIZE = 36
TITLE_FONT_SIZE = 64
TITLE_LINE_HEIGHT = 76
TITLE_MAX_LINES = 2
TITLE_TOP = 116
POINT_FONT_SIZE = 36
POINT_LINE_HEIGHT = 42
POINT_GAP = 14
POINT_NUMBER_INDENT = 56
POINT_TOP = 296
FOOTER_FONT_SIZE = 30
FOOTER_TOP = HEIGHT - 54

ELLIPSIS = "…"


def load_share_card(cache_dir: str | Path) -> Optional[Dict[str, Any]]:
    """Read and validate llm_share_card.json from a task cache directory.

    Returns the normalized card dict, or None when the file is missing or
    violates the contract (invalid cards are treated as "no card").
    """
    path = Path(cache_dir) / CARD_FILENAME
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        logger.warning("分享卡片 JSON 读取失败 {}: {}", path, exc)
        return None

    if not isinstance(data, dict) or data.get("version") != 1:
        logger.warning("分享卡片不合契约 {}: version 必须为 1", path)
        return None
    headline = data.get("headline")
    points = data.get("points")
    if not isinstance(headline, str) or not headline.strip():
        logger.warning("分享卡片不合契约 {}: headline 必须为非空字符串", path)
        return None
    if (
        not isinstance(points, list)
        or not 1 <= len(points) <= 3
        or not all(isinstance(p, str) and p.strip() for p in points)
    ):
        logger.warning("分享卡片不合契约 {}: points 必须为 1 到 3 条非空字符串", path)
        return None
    generated_at = data.get("generated_at")
    if generated_at is not None and not isinstance(generated_at, str):
        logger.warning("分享卡片不合契约 {}: generated_at 必须为字符串", path)
        return None
    return {
        "headline": headline.strip(),
        "points": [p.strip() for p in points],
        "generated_at": generated_at,
    }


def _tokenize(text: str) -> List[str]:
    """Split text into wrap units: one CJK char each, latin words, spaces."""
    tokens: List[str] = []
    word = ""
    for ch in text:
        if ch.isspace():
            if word:
                tokens.append(word)
                word = ""
            tokens.append(" ")
        elif unicodedata.east_asian_width(ch) in ("W", "F"):
            if word:
                tokens.append(word)
                word = ""
            tokens.append(ch)
        else:
            word += ch
    if word:
        tokens.append(word)
    return tokens


def _text_width(draw: ImageDraw.ImageDraw, text: str, font) -> float:
    return draw.textlength(text, font=font)


def wrap_text(text: str, font, max_width: int, draw: ImageDraw.ImageDraw) -> List[str]:
    """Greedy line wrapping; CJK breaks per char, latin breaks per word.

    A single unit wider than max_width (long URL etc.) is hard-broken.
    """
    lines: List[str] = []
    current = ""
    for token in _tokenize(text):
        if token == " ":
            if not current:
                continue
            if _text_width(draw, current + " ", font) <= max_width:
                current += " "
            else:
                lines.append(current)
                current = ""
            continue
        if _text_width(draw, current + token, font) <= max_width:
            current += token
            continue
        if current:
            lines.append(current)
            current = ""
        if _text_width(draw, token, font) > max_width:
            while _text_width(draw, token, font) > max_width and len(token) > 1:
                cut = 1
                while (
                    cut < len(token)
                    and _text_width(draw, token[: cut + 1], font) <= max_width
                ):
                    cut += 1
                lines.append(token[:cut])
                token = token[cut:]
        current = token
    if current:
        lines.append(current)
    return lines or [""]


def truncate_lines(
    text: str,
    font,
    max_width: int,
    draw: ImageDraw.ImageDraw,
    max_lines: int,
) -> List[str]:
    """Wrap then cap at max_lines, marking overflow with an ellipsis."""
    lines = wrap_text(text, font, max_width, draw)
    if len(lines) <= max_lines:
        return lines
    kept = lines[:max_lines]
    last = kept[-1]
    while last and _text_width(draw, last + ELLIPSIS, font) > max_width:
        last = last[:-1]
    kept[-1] = last + ELLIPSIS
    return kept


def _load_font(path: str | Path, size: int):
    """Load a font, failing loudly when the configured file is missing.

    Debian's Noto CJK files are .ttc collections whose face 0 is the JP
    variant; when the default face is not SC, scan the collection for the SC
    face so Simplified Chinese text gets SC glyph variants.
    """
    font_path = Path(path)
    if not font_path.is_file():
        logger.error("OG 卡片字体文件不存在: {}", font_path)
        raise FileNotFoundError(f"OG card font not found: {font_path}")
    font = ImageFont.truetype(str(font_path), size)
    if font_path.suffix.lower() == ".ttc":
        family = font.getname()[0].lower()
        if "sc" not in family:
            for index in range(1, 16):
                try:
                    candidate = ImageFont.truetype(str(font_path), size, index=index)
                except OSError:
                    break
                if "sc" in candidate.getname()[0].lower():
                    return candidate
    return font


def render_og_card(
    card: Dict[str, Any],
    *,
    platform_display: str,
    author: str,
    site_url: str,
    font_path: str | Path = DEFAULT_FONT_PATH,
    font_bold_path: str | Path = DEFAULT_FONT_BOLD_PATH,
    output_path: str | Path,
) -> Path:
    """Render a share card to output_path (atomically) and return its path."""
    header_font = _load_font(font_path, HEADER_FONT_SIZE)
    title_font = _load_font(font_bold_path, TITLE_FONT_SIZE)
    point_font = _load_font(font_path, POINT_FONT_SIZE)
    footer_font = _load_font(font_path, FOOTER_FONT_SIZE)

    image = Image.new("RGB", (WIDTH, HEIGHT), BG_COLOR)
    draw = ImageDraw.Draw(image)

    # Brand accent bar across the top.
    draw.rectangle([0, 0, WIDTH, 8], fill=ACCENT_COLOR)

    header = " · ".join(part for part in (platform_display, author) if part)
    draw.text((MARGIN, 52), header, font=header_font, fill=HEADER_COLOR)

    for i, line in enumerate(
        truncate_lines(card["headline"], title_font, CONTENT_WIDTH, draw, TITLE_MAX_LINES)
    ):
        draw.text((MARGIN, TITLE_TOP + i * TITLE_LINE_HEIGHT), line, font=title_font, fill=TITLE_COLOR)

    y = POINT_TOP
    for number, point in enumerate(card["points"], start=1):
        lines = truncate_lines(
            point, point_font, CONTENT_WIDTH - POINT_NUMBER_INDENT, draw, TITLE_MAX_LINES
        )
        draw.text((MARGIN, y), f"{number}.", font=point_font, fill=ACCENT_COLOR)
        for i, line in enumerate(lines):
            draw.text(
                (MARGIN + POINT_NUMBER_INDENT, y + i * POINT_LINE_HEIGHT),
                line,
                font=point_font,
                fill=POINT_COLOR,
            )
        y += POINT_LINE_HEIGHT * len(lines) + POINT_GAP

    host = urlparse(site_url).hostname or site_url
    draw.text((MARGIN, FOOTER_TOP), host, font=footer_font, fill=FOOTER_COLOR)
    ai_label = "AI 总结"
    label_width = _text_width(draw, ai_label, footer_font)
    draw.text(
        (WIDTH - MARGIN - label_width, FOOTER_TOP),
        ai_label,
        font=footer_font,
        fill=ACCENT_COLOR,
    )

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=output.parent, suffix=".png.tmp")
    try:
        with os.fdopen(fd, "wb") as tmp_file:
            image.save(tmp_file, "PNG")
        os.replace(tmp_name, output)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise
    return output
