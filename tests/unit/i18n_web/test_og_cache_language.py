"""OG PNG cache files are split by UI language.

All console output must be in English only (no emoji, no Chinese).
"""

from pathlib import Path

from video_transcript_api.i18n import t
from video_transcript_api.utils.rendering.og_card import png_filename, render_og_card

FONTS_DIR = Path(__file__).resolve().parents[2] / "og_card" / "fonts"
REGULAR_FONT = FONTS_DIR / "NotoSansSC-Regular-subset.ttf"
BOLD_FONT = FONTS_DIR / "NotoSansSC-Bold-subset.ttf"

CARD = {
    "headline": "Hello headline",
    "points": ["Point one", "Point two"],
}


def test_png_filename_includes_language(language_config):
    language_config("zh-CN")
    assert png_filename() == "og_card.zh-CN.png"
    language_config("en")
    assert png_filename() == "og_card.en.png"
    assert png_filename() != "og_card.png"


def test_same_cache_dir_keeps_language_pngs_apart(language_config, tmp_path):
    assert REGULAR_FONT.is_file(), f"fixture font missing: {REGULAR_FONT}"
    assert BOLD_FONT.is_file(), f"fixture font missing: {BOLD_FONT}"
    stale = tmp_path / "og_card.png"
    stale.write_bytes(b"stale-unmigrated")

    language_config("zh-CN")
    zh_path = tmp_path / png_filename()
    render_og_card(
        CARD,
        platform_display="YouTube",
        author="Author",
        site_url="https://example.com",
        font_path=REGULAR_FONT,
        font_bold_path=BOLD_FONT,
        output_path=zh_path,
    )

    language_config("en")
    assert t("og.ai_label") == "AI Summary"
    en_path = tmp_path / png_filename()
    render_og_card(
        CARD,
        platform_display="YouTube",
        author="Author",
        site_url="https://example.com",
        font_path=REGULAR_FONT,
        font_bold_path=BOLD_FONT,
        output_path=en_path,
    )

    assert zh_path != en_path
    assert zh_path.name == "og_card.zh-CN.png"
    assert en_path.name == "og_card.en.png"
    assert zh_path.is_file()
    assert en_path.is_file()
    assert zh_path.read_bytes() != en_path.read_bytes()
    assert stale.read_bytes() == b"stale-unmigrated"
    assert not any(path.name == "og_card.png" and path != stale for path in tmp_path.iterdir())
