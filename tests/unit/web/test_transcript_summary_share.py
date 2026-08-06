"""Structural and rendering contracts for summary ratio guidance and sharing."""

from pathlib import Path

import jinja2


PROJECT_ROOT = Path(__file__).resolve().parents[3]
TEMPLATES_DIR = PROJECT_ROOT / "src" / "web" / "templates"
TRANSCRIPT_TEMPLATE = TEMPLATES_DIR / "transcript.html"
BASE_TEMPLATE = TEMPLATES_DIR / "base.html"


def _jinja_env() -> jinja2.Environment:
    return jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=True,
    )


def _base_context(**overrides) -> dict:
    context = {
        "title": "Sample Video Title",
        "url": "https://example.com/video/123",
        "author": "Sample Author",
        "created_at_display": "2026-07-11 10:00",
        "platform": "youtube",
        "summary_html": "<p>First summary paragraph.</p><p>Second paragraph.</p>",
        "calibrated_html": "<p>Calibrated body.</p>",
        "view_token": "test-view-token-123",
        "stats": {
            "original_length": 250,
            "calibrated_length": 100,
            "summary_length": 123,
        },
        "llm_config": None,
    }
    context.update(overrides)
    return context


def _render(**overrides) -> str:
    return _jinja_env().get_template("transcript.html").render(**_base_context(**overrides))


class TestSummaryRatioGuidance:
    def test_formats_summary_ratio_to_one_decimal_place(self):
        html = _render()
        assert "内容总结 123 字（占原文 49.2%）" in html

    def test_shows_condensation_hint_at_or_below_twenty_percent(self):
        html = _render(
            stats={"original_length": 100, "calibrated_length": 80, "summary_length": 20}
        )
        assert "内容高度浓缩，可能省略较多细节。" in html

    def test_threshold_uses_displayed_one_decimal_ratio(self):
        html = _render(
            stats={"original_length": 100_000, "calibrated_length": 80_000, "summary_length": 20_001}
        )
        assert "占原文 20.0%" in html
        assert "内容高度浓缩，可能省略较多细节。" in html

    def test_omits_condensation_hint_above_twenty_percent(self):
        html = _render(
            stats={"original_length": 100, "calibrated_length": 80, "summary_length": 21}
        )
        assert "内容高度浓缩，可能省略较多细节。" not in html

    def test_condensation_advice_mentions_notes_when_available(self):
        html = _render(
            stats={
                "original_length": 100,
                "calibrated_length": 80,
                "summary_length": 20,
                "notes_length": 300,
            },
            notes_html="<p>Detailed notes.</p>",
        )
        assert "建议阅读详细笔记或原文。" in html
        assert "建议生成详细笔记或阅读原文。" not in html

    def test_condensation_advice_suggests_generating_notes_when_absent(self):
        html = _render(
            stats={"original_length": 100, "calibrated_length": 80, "summary_length": 20}
        )
        assert "建议生成详细笔记或阅读原文。" in html

    def test_notes_length_without_rendered_notes_suggests_generating_notes(self):
        html = _render(
            stats={
                "original_length": 100,
                "calibrated_length": 80,
                "summary_length": 20,
                "notes_length": 300,
            },
            notes_html=None,
        )
        assert "建议生成详细笔记或阅读原文。" in html
        assert "建议阅读详细笔记或原文。" not in html

    def test_zero_lengths_do_not_render_ratio_or_hint(self):
        zero_original = _render(
            stats={"original_length": 0, "calibrated_length": 0, "summary_length": 10}
        )
        zero_summary = _render(
            stats={"original_length": 100, "calibrated_length": 80, "summary_length": 0}
        )
        for html in (zero_original, zero_summary):
            assert "占原文" not in html
            assert "内容高度浓缩，可能省略较多细节。" not in html


class TestSummaryShareButton:
    def test_button_requires_view_token_and_summary_html(self):
        share_button = 'class="quick-copy-btn share-summary-btn"'
        assert share_button in _render()
        assert share_button not in _render(view_token=None)
        assert share_button not in _render(summary_html="")

    def test_share_builder_uses_canonical_view_url_and_first_paragraph(self):
        source = TRANSCRIPT_TEMPLATE.read_text(encoding="utf-8")
        assert "function buildSummaryShareText()" in source
        assert "window.location.origin + '/view/' + encodeURIComponent(summaryShareViewToken)" in source
        assert "document.getElementById('summary-content-block')" in source
        assert "summaryBlock.querySelector('p')" in source
        assert "paragraph.innerText || paragraph.textContent" in source
        assert "shareLines.push('', summaryParagraph)" in source
        assert "window.location.href" not in source

    def test_share_copy_reuses_clipboard_helper_and_excludes_generic_url_listener(self):
        transcript_source = TRANSCRIPT_TEMPLATE.read_text(encoding="utf-8")
        base_source = BASE_TEMPLATE.read_text(encoding="utf-8")
        assert "copyTextToClipboard(buildSummaryShareText()" in transcript_source
        assert "function copyTextToClipboard(" in base_source
        assert ".quick-copy-btn:not(.deep-read-prompt-btn):not(.share-summary-btn)" in base_source
        assert "shareButton.classList.add('copied')" in transcript_source

    def test_title_url_and_token_are_json_escaped_for_script_injection(self):
        html = _render(
            title='</script><script>alert("title")</script>',
            url='https://example.com/video?quote="&amp;\'\n',
            view_token='token"><script>alert("token")</script>',
        )
        assert '<script>alert("title")</script>' not in html
        assert '<script>alert("token")</script>' not in html
        assert "summaryShareTitle" in html
        assert "summaryShareOriginalUrl" in html
        assert "summaryShareViewToken" in html

    def test_share_text_format_documents_optional_original_url_line(self):
        source = TRANSCRIPT_TEMPLATE.read_text(encoding="utf-8")
        assert "shareLines.push('原始地址：' + summaryShareOriginalUrl)" in source
        assert "shareLines.push('', '总结和校对：'" in source
        assert "shareLines.join('\\n')" in source
