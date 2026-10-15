"""Unit tests for the OG share-card renderer (og_card.py).

Rendering tests use the committed subset fonts in tests/og_card/fonts/ and
never depend on system fonts; if those fixture files are missing the tests
fail (no skip). The subsets are built from every non-ASCII character in
tests/og_card/*.py -- rerun fonts/build_subsets.py after adding text.

All console output must be in English only (no emoji, no Chinese).
"""

import json
from pathlib import Path

import pytest
from PIL import Image, ImageDraw, ImageFont

from video_transcript_api.utils.rendering import og_card
from video_transcript_api.utils.rendering.og_card import (
    CONTENT_WIDTH,
    TITLE_MAX_LINES,
    layout_footer_host,
    layout_header,
    load_share_card,
    render_og_card,
    truncate_lines,
    wrap_text,
)

FONTS_DIR = Path(__file__).parent / "fonts"
REGULAR_FONT = FONTS_DIR / "NotoSansSC-Regular-subset.ttf"
BOLD_FONT = FONTS_DIR / "NotoSansSC-Bold-subset.ttf"

HEADLINE = "用 AI 三分钟读懂这场关于大模型未来的深度对谈"
POINTS = [
    "Scaling Law 撞墙后，推理能力成为新的分水岭",
    "OpenAI 与 Anthropic 的路线分歧逐条拆解",
    "给开发者的三条可落地行动建议",
]
LONG_HEADLINE = "超长标题压力测试用例逐字折行与省略号" * 10
LONG_POINT = "这条要点远超契约长度上限，用来验证逐字折行与省略号截断，绝不溢出画布边界" * 4
WRAP_MIXED = "在 Boston Dynamics 的最新 Demo 里，Atlas 完成了 127 项连续任务"
CJK_WRAP = "深度学习模型的安全对齐问题正在成为行业共识，需要更多可复现的评测基准来支撑日常的迭代决策"

CARD = {
    "version": 1,
    "headline": HEADLINE,
    "points": POINTS,
    "generated_at": "2026-10-15T16:00:00+08:00",
}


@pytest.fixture
def draw() -> ImageDraw.ImageDraw:
    return ImageDraw.Draw(Image.new("RGB", (10, 10)))


@pytest.fixture
def regular_font():
    assert REGULAR_FONT.is_file(), (
        f"fixture font missing: {REGULAR_FONT}; rerun fonts/build_subsets.py"
    )
    return ImageFont.truetype(str(REGULAR_FONT), 36)


@pytest.fixture
def bold_font():
    assert BOLD_FONT.is_file(), (
        f"fixture font missing: {BOLD_FONT}; rerun fonts/build_subsets.py"
    )
    return ImageFont.truetype(str(BOLD_FONT), 64)


def _write_card(cache_dir: Path, card) -> Path:
    path = cache_dir / og_card.CARD_FILENAME
    path.write_text(json.dumps(card, ensure_ascii=False), encoding="utf-8")
    return path


class TestLoadShareCard:
    def test_missing_file_returns_none(self, tmp_path):
        assert load_share_card(tmp_path) is None

    def test_valid_card_normalized(self, tmp_path):
        _write_card(tmp_path, CARD)
        card = load_share_card(tmp_path)
        assert card == {
            "headline": HEADLINE,
            "points": POINTS,
            "generated_at": "2026-10-15T16:00:00+08:00",
        }

    def test_invalid_version_returns_none(self, tmp_path):
        _write_card(tmp_path, {**CARD, "version": 2})
        assert load_share_card(tmp_path) is None

    def test_headline_not_string_returns_none(self, tmp_path):
        _write_card(tmp_path, {**CARD, "headline": 42})
        assert load_share_card(tmp_path) is None

    @pytest.mark.parametrize("points", [[], POINTS + ["第四条"]])
    def test_points_out_of_range_returns_none(self, tmp_path, points):
        _write_card(tmp_path, {**CARD, "points": points})
        assert load_share_card(tmp_path) is None

    def test_points_non_string_element_returns_none(self, tmp_path):
        _write_card(tmp_path, {**CARD, "points": ["ok", None]})
        assert load_share_card(tmp_path) is None

    def test_malformed_json_returns_none(self, tmp_path):
        (tmp_path / og_card.CARD_FILENAME).write_text("{not json", encoding="utf-8")
        assert load_share_card(tmp_path) is None

    def test_generated_at_missing_returns_none(self, tmp_path):
        card = {k: v for k, v in CARD.items() if k != "generated_at"}
        _write_card(tmp_path, card)
        assert load_share_card(tmp_path) is None

    @pytest.mark.parametrize(
        "override",
        [
            pytest.param({"headline": ""}, id="headline-empty"),
            pytest.param({"headline": "标" * 31}, id="headline-too-long"),
            pytest.param({"points": ["x" * 81]}, id="point-too-long"),
            pytest.param({"generated_at": ""}, id="generated-at-empty"),
            pytest.param(
                {"generated_at": "not-a-timestamp"}, id="generated-at-invalid"
            ),
        ],
    )
    def test_contract_violation_returns_none(self, tmp_path, override):
        _write_card(tmp_path, {**CARD, **override})
        assert load_share_card(tmp_path) is None


class TestWrapText:
    def test_cjk_wraps_per_char(self, draw, regular_font):
        lines = wrap_text(CJK_WRAP, regular_font, 400, draw)
        assert len(lines) >= 3
        assert all(
            draw.textlength(line, font=regular_font) <= 400 for line in lines
        )
        assert "".join(lines) == CJK_WRAP

    def test_latin_wraps_per_word(self, draw, regular_font):
        text = "alpha beta gamma delta epsilon zeta"
        lines = wrap_text(text, regular_font, 220, draw)
        assert len(lines) >= 2
        for line in lines:
            assert draw.textlength(line, font=regular_font) <= 220
            # No word is split across lines.
            for word in line.split():
                assert word in text.split()

    def test_mixed_wraps_without_losing_content(self, draw, regular_font):
        lines = wrap_text(WRAP_MIXED, regular_font, 300, draw)
        assert len(lines) >= 2
        assert all(
            draw.textlength(line, font=regular_font) <= 300 for line in lines
        )
        assert "".join(lines).replace(" ", "") == WRAP_MIXED.replace(" ", "")

    def test_oversized_word_hard_breaks(self, draw, regular_font):
        text = "A" * 200
        lines = wrap_text(text, regular_font, 300, draw)
        assert len(lines) >= 2
        assert all(
            draw.textlength(line, font=regular_font) <= 300 for line in lines
        )
        assert "".join(lines) == text


class TestTruncateLines:
    def test_fitting_text_unchanged(self, draw, regular_font):
        text = "短标题一行放得下"
        assert truncate_lines(text, regular_font, 500, draw, 2) == [text]

    def test_overflow_caps_with_ellipsis(self, draw, regular_font):
        lines = truncate_lines(LONG_POINT, regular_font, 400, draw, 2)
        assert len(lines) == 2
        assert lines[-1].endswith(og_card.ELLIPSIS)
        assert all(
            draw.textlength(line, font=regular_font) <= 400 for line in lines
        )

    def test_headline_overflow_caps_at_two_lines(self, draw, bold_font):
        lines = truncate_lines(
            LONG_HEADLINE, bold_font, CONTENT_WIDTH, draw, TITLE_MAX_LINES
        )
        assert len(lines) == TITLE_MAX_LINES
        assert lines[-1].endswith(og_card.ELLIPSIS)


class TestLayoutBounds:
    """F4: header and footer host must truncate to stay inside the canvas
    and clear of the footer AI label. Asserted on the same layout helpers
    the renderer calls (no pixel comparison)."""

    def test_long_author_header_fits_content_width(self, draw, regular_font):
        line = layout_header("哔哩哔哩", "超长作者名称测试" * 30, draw, regular_font)
        assert draw.textlength(line, font=regular_font) <= CONTENT_WIDTH
        assert line.endswith(og_card.ELLIPSIS)

    def test_long_host_stays_clear_of_ai_label(self, draw):
        font = ImageFont.truetype(str(REGULAR_FONT), og_card.FOOTER_FONT_SIZE)
        host = layout_footer_host(
            "very-long-subdomain." * 24 + "example.com", draw, font
        )
        host_right = og_card.MARGIN + draw.textlength(host, font=font)
        label_left = (
            og_card.WIDTH - og_card.MARGIN - draw.textlength(og_card.AI_LABEL, font=font)
        )
        assert host_right + og_card.FOOTER_GAP <= label_left

    def test_render_with_long_header_and_host_smoke(self, tmp_path):
        out = tmp_path / "og_card.png"
        render_og_card(
            CARD,
            platform_display="哔哩哔哩",
            author="超长作者名称测试" * 30,
            site_url="https://very-long-subdomain." + "x" * 200 + ".example.com",
            font_path=REGULAR_FONT,
            font_bold_path=BOLD_FONT,
            output_path=out,
        )
        with Image.open(out) as img:
            assert img.size == (og_card.WIDTH, og_card.HEIGHT)


class TestRenderOgCard:
    def test_render_produces_1200x630_png(self, tmp_path):
        out = tmp_path / "og_card.png"
        result = render_og_card(
            CARD,
            platform_display="YouTube",
            author="AI 前沿观察",
            site_url="https://sum.zlxlabs.com/view/tok",
            font_path=REGULAR_FONT,
            font_bold_path=BOLD_FONT,
            output_path=out,
        )
        assert result == out
        with Image.open(out) as img:
            assert img.size == (og_card.WIDTH, og_card.HEIGHT)
            assert img.format == "PNG"

    def test_render_with_overflowing_content_stays_in_canvas(self, tmp_path):
        out = tmp_path / "og_card.png"
        render_og_card(
            {
                "version": 1,
                "headline": LONG_HEADLINE,
                "points": [LONG_POINT, LONG_POINT, LONG_POINT],
                "generated_at": None,
            },
            platform_display="哔哩哔哩",
            author="AI 前沿观察",
            site_url="https://sum.zlxlabs.com/view/tok",
            font_path=REGULAR_FONT,
            font_bold_path=BOLD_FONT,
            output_path=out,
        )
        with Image.open(out) as img:
            assert img.size == (og_card.WIDTH, og_card.HEIGHT)

    def test_missing_font_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            render_og_card(
                CARD,
                platform_display="YouTube",
                author="作者",
                site_url="https://sum.zlxlabs.com",
                font_path=tmp_path / "missing.ttf",
                font_bold_path=BOLD_FONT,
                output_path=tmp_path / "og_card.png",
            )

    def test_missing_bold_font_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            render_og_card(
                CARD,
                platform_display="YouTube",
                author="作者",
                site_url="https://sum.zlxlabs.com",
                font_path=REGULAR_FONT,
                font_bold_path=tmp_path / "missing-bold.ttf",
                output_path=tmp_path / "og_card.png",
            )

    def test_atomic_write_leaves_no_temp_files(self, tmp_path):
        out = tmp_path / "og_card.png"
        render_og_card(
            CARD,
            platform_display="YouTube",
            author="作者",
            site_url="https://sum.zlxlabs.com",
            font_path=REGULAR_FONT,
            font_bold_path=BOLD_FONT,
            output_path=out,
        )
        assert out.is_file()
        assert list(tmp_path.iterdir()) == [out]
