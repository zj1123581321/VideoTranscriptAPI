"""View preparation and template tests for detailed notes.

All console output must stay ASCII-only.
"""

import json
from pathlib import Path
from unittest.mock import patch

import jinja2
import pytest

from video_transcript_api.api.routes.views import (
    _add_notes_chapter_anchors,
    _prepare_success_view,
    load_notes_anchor_chapters,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEMPLATES_DIR = PROJECT_ROOT / "src" / "web" / "templates"


def test_prepare_success_view_renders_notes_with_chapter_anchors(tmp_path):
    (tmp_path / "llm_notes.txt").write_text(
        "## [00:00:00 - 00:01:00] Intro\n- **Key claim**\n\n"
        "## [00:01:00 - 00:02:00] Detail\n- Fact",
        encoding="utf-8",
    )
    (tmp_path / "llm_status.json").write_text(
        json.dumps(
            {
                "chapters_status": "generated",
                "notes_status": "generated",
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "llm_chapters.json").write_text(
        json.dumps(
            {
                "chapters": [
                    {
                        "index": 0,
                        "title": "Intro",
                        "start_time": 0,
                        "end_time": 60,
                    },
                    {
                        "index": 1,
                        "title": "Detail",
                        "start_time": 60,
                        "end_time": 120,
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    view_data = {
        "cache_dir": str(tmp_path),
        "summary": None,
        "notes": (
            "## [00:00:00 - 00:01:00] Intro\n- **Key claim**\n\n"
            "## [00:01:00 - 00:02:00] Detail\n- Fact"
        ),
        "notes_state": "generated",
    }

    with patch(
        "video_transcript_api.api.routes.views.get_config",
        return_value={"llm": {}},
    ):
        stats = _prepare_success_view(view_data)

    assert stats["notes_length"] > 0
    assert stats["notes_status"] == "generated"
    assert 'id="notes-chapter-0"' in view_data["notes_html"]
    assert 'id="notes-chapter-1"' in view_data["notes_html"]
    assert 'id="intro"' not in view_data["notes_html"]
    assert 'id="detail"' not in view_data["notes_html"]
    assert "<strong>Key claim</strong>" in view_data["notes_html"]


@pytest.mark.parametrize(
    ("title", "notes_html", "chapter_index"),
    [
        (
            "Understanding **bold**",
            "<h2>Understanding <strong>bold</strong></h2>",
            7,
        ),
        ("A  B", "<h2>A B</h2>", 8),
        ("Rock & Roll", "<h2>Rock &amp; Roll</h2>", 9),
    ],
)
def test_notes_anchors_match_titles_after_markdown_rendering(
    title, notes_html, chapter_index
):
    chapters = [
        {"index": chapter_index, "title": title, "start_time": None, "end_time": None}
    ]

    result = _add_notes_chapter_anchors(notes_html, chapters)

    assert f'id="notes-chapter-{chapter_index}"' in result


def test_notes_anchor_title_normalization_does_not_cascade_after_first_chapter():
    chapters = [
        {
            "index": 3,
            "title": "Understanding **bold**",
            "start_time": None,
            "end_time": None,
        },
        {"index": 4, "title": "Second", "start_time": None, "end_time": None},
        {"index": 5, "title": "Third", "start_time": None, "end_time": None},
    ]
    notes_html = (
        "<h2>Understanding <strong>bold</strong></h2>"
        "<h2>Second</h2>"
        "<h2>Third</h2>"
    )

    result = _add_notes_chapter_anchors(notes_html, chapters)

    assert '<h2 id="notes-chapter-3">Understanding <strong>bold</strong></h2>' in result
    assert '<h2 id="notes-chapter-4">Second</h2>' in result
    assert '<h2 id="notes-chapter-5">Third</h2>' in result


@pytest.mark.parametrize(
    ("first_title", "rendered_first_title"),
    [("1. 概述", "1. 概述"), ("# 深入", "# 深入"), ("深入 #", "深入")],
)
def test_notes_anchors_continue_after_block_markdown_title(
    first_title, rendered_first_title
):
    chapters = [
        {"index": 0, "title": first_title, "start_time": None, "end_time": None},
        {"index": 1, "title": "第二章", "start_time": None, "end_time": None},
        {"index": 2, "title": "第三章", "start_time": None, "end_time": None},
    ]
    notes_html = (
        f"<h2>[00:00:00 - 00:01:00] {rendered_first_title}</h2>"
        "<h2>第二章</h2>"
        "<h2>第三章</h2>"
    )

    result = _add_notes_chapter_anchors(notes_html, chapters)

    assert '<h2 id="notes-chapter-0">' in result
    assert '<h2 id="notes-chapter-1">第二章</h2>' in result
    assert '<h2 id="notes-chapter-2">第三章</h2>' in result


def test_notes_anchor_rendering_failure_skips_injecting_entire_chapter_group():
    chapters = [
        {"index": 0, "title": "First", "start_time": None, "end_time": None},
        {"index": 1, "title": "Second", "start_time": None, "end_time": None},
    ]
    notes_html = "<h2>First</h2><h2>Second</h2>"

    with (
        patch(
            "video_transcript_api.api.routes.views.render_markdown_to_html",
            side_effect=["<p>First</p>", RuntimeError("renderer unavailable")],
        ),
        patch("video_transcript_api.api.routes.views.logger.warning") as warning,
    ):
        result = _add_notes_chapter_anchors(notes_html, chapters)

    assert result == notes_html
    warning.assert_called_once_with(
        "Notes chapter anchors skipped: chapter list unavailable"
    )


def test_notes_anchors_match_titles_with_different_persisted_times():
    chapters = [
        {
            "index": 7,
            "title": "C++ [intro].",
            "start_time": 600,
            "end_time": None,
        },
        {
            "index": 11,
            "title": "Second",
            "start_time": None,
            "end_time": None,
        },
    ]
    notes_html = (
        '<h2 class="first">[00:10:00 - 00:12:00] C++ [intro].</h2>'
        "<p>First</p>"
        "<h2>Second</h2>"
    )

    result = _add_notes_chapter_anchors(notes_html, chapters)

    assert 'id="notes-chapter-7"' in result
    assert 'id="notes-chapter-11"' in result
    assert 'id="notes-chapter-0"' not in result


def test_notes_anchors_do_not_cascade_after_time_mismatch():
    chapters = [
        {"index": 0, "title": "First", "start_time": 0, "end_time": 60},
        {"index": 1, "title": "Second", "start_time": 720, "end_time": 840},
        {"index": 2, "title": "Third", "start_time": 840, "end_time": 960},
    ]
    notes_html = (
        "<h2>[00:10:00 - 00:12:00] First</h2>"
        "<h2>[00:12:00 - 00:14:00] Second</h2>"
        "<h2>[00:14:00 - 00:16:00] Third</h2>"
    )

    result = _add_notes_chapter_anchors(notes_html, chapters)

    assert 'id="notes-chapter-0"' in result
    assert 'id="notes-chapter-1"' in result
    assert 'id="notes-chapter-2"' in result


def test_notes_anchor_mismatch_does_not_advance_chapter_pointer():
    chapters = [
        {"index": 3, "title": "First", "start_time": None, "end_time": None},
        {"index": 4, "title": "Second", "start_time": None, "end_time": None},
    ]
    notes_html = "<h2>Unrelated</h2><h2>First</h2><h2>Second</h2>"

    result = _add_notes_chapter_anchors(notes_html, chapters)

    assert result.startswith("<h2>Unrelated</h2>")
    assert '<h2 id="notes-chapter-3">First</h2>' in result
    assert '<h2 id="notes-chapter-4">Second</h2>' in result


def test_notes_anchor_skips_noise_and_matches_timed_nonconsecutive_indices():
    chapters = [
        {
            "index": 4,
            "title": "Rust 1.0 (稳定版) [重要]",
            "start_time": 0,
            "end_time": 61,
        },
        {
            "index": 12,
            "title": "后续内容",
            "start_time": 61,
            "end_time": 122,
        },
    ]
    notes_html = (
        "<h2>本章概要</h2>"
        "<h2>[00:10:00 - 00:12:00] Rust 1.0 (稳定版) [重要]</h2>"
        "<h2>Rust 1.0 (稳定版) [重要]</h2>"
        "<h2>详细内容</h2>"
        "<h2>[00:12:00 - 00:14:00] 后续内容</h2>"
    )

    result = _add_notes_chapter_anchors(notes_html, chapters)

    assert '<h2>本章概要</h2>' in result
    assert '<h2>Rust 1.0 (稳定版) [重要]</h2>' in result
    assert '<h2>详细内容</h2>' in result
    assert '<h2 id="notes-chapter-4">[00:10:00 - 00:12:00] Rust 1.0 (稳定版) [重要]</h2>' in result
    assert '<h2 id="notes-chapter-12">[00:12:00 - 00:14:00] 后续内容</h2>' in result


def test_notes_anchor_does_not_reuse_consumed_chapter_for_duplicate_bare_title():
    chapters = [
        {"index": 0, "title": "First", "start_time": None, "end_time": None},
        {"index": 1, "title": "Second", "start_time": None, "end_time": None},
    ]
    notes_html = "<h2>First</h2><h2>First</h2><h2>Second</h2>"

    result = _add_notes_chapter_anchors(notes_html, chapters)

    assert result.count('id="notes-chapter-0"') == 1
    assert '<h2>First</h2>' in result
    assert '<h2 id="notes-chapter-1">Second</h2>' in result


def test_notes_anchor_rejects_invalid_time_prefix_without_advancing_pointer():
    chapters = [{"index": 0, "title": "标题", "start_time": None, "end_time": None}]
    notes_html = "<h2>[备注] 标题</h2><h2>标题</h2>"

    result = _add_notes_chapter_anchors(notes_html, chapters)

    assert "<h2>[备注] 标题</h2>" in result
    assert '<h2 id="notes-chapter-0">标题</h2>' in result


def test_notes_anchor_overwrites_chapter_id_and_preserves_nonchapter_attributes():
    chapters = [{"index": 5, "title": "First", "start_time": None, "end_time": None}]
    notes_html = (
        '<h2 class="chapter" id="old-id" data-kind="notes">First</h2>'
        '<h2 class="keep" id="keep-id" data-kind="other">Unrelated</h2>'
    )

    result = _add_notes_chapter_anchors(notes_html, chapters)

    assert '<h2 id="notes-chapter-5" class="chapter" data-kind="notes">First</h2>' in result
    assert '<h2 class="keep" id="keep-id" data-kind="other">Unrelated</h2>' in result


@pytest.mark.parametrize(
    "cache_setup",
    [
        "missing",
        "corrupt",
        "wrong_shape",
        "empty",
        "read_failure",
    ],
)
def test_unavailable_notes_anchor_chapters_leave_html_unchanged(tmp_path, cache_setup):
    if cache_setup == "corrupt":
        (tmp_path / "llm_chapters.json").write_text("{", encoding="utf-8")
    elif cache_setup == "wrong_shape":
        (tmp_path / "llm_chapters.json").write_text(
            json.dumps({"chapters": "not-a-list"}), encoding="utf-8"
        )
    elif cache_setup == "empty":
        (tmp_path / "llm_chapters.json").write_text(
            json.dumps({"chapters": []}), encoding="utf-8"
        )
    elif cache_setup == "read_failure":
        cache_file = tmp_path / "cache-file"
        cache_file.write_text("not-a-directory", encoding="utf-8")
        tmp_path = cache_file

    notes_html = '<h2 id="keep">First</h2>'
    chapters = load_notes_anchor_chapters(tmp_path)

    with patch("video_transcript_api.api.routes.views.logger.warning") as warning:
        result = _add_notes_chapter_anchors(notes_html, chapters)

    assert result == notes_html
    warning.assert_called_once_with(
        "Notes chapter anchors skipped: chapter list unavailable"
    )


def test_notes_anchors_ignore_chapter_status_and_jump_gates(tmp_path):
    (tmp_path / "llm_chapters.json").write_text(
        json.dumps(
            {
                "chapters": [
                    {"index": 0, "title": "First", "start_time": None, "end_time": None}
                ]
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "llm_status.json").write_text(
        json.dumps({"chapters_status": "failed", "notes_status": "generated"}),
        encoding="utf-8",
    )
    view_data = {
        "cache_dir": str(tmp_path),
        "summary": None,
        "notes": "## First\n- Fact",
        "notes_state": "generated",
    }

    with patch(
        "video_transcript_api.api.routes.views.get_config",
        return_value={"llm": {}},
    ):
        _prepare_success_view(view_data)

    assert '<h2 id="notes-chapter-0">First</h2>' in view_data["notes_html"]


def _render_notes_template(**overrides):
    environment = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=True,
    )
    context = {
        "title": "Demo",
        "author": "Owner",
        "url": "https://example.com/demo",
        "platform": "youtube",
        "created_at_display": "2026-07-28 20:00",
        "summary_html": "<p>Summary</p>",
        "summary_state": "generated",
        "notes_html": None,
        "notes_state": None,
        "calibrated_html": "<p>Transcript</p>",
        "chapters_data": None,
        "deep_read_prompt_presets": [],
        "use_speaker_recognition": False,
        "view_token": "view-notes",
        "asset_v": "test",
        "llm_config": None,
        "stats": {
            "original_length": 100,
            "calibrated_length": 90,
            "summary_length": 20,
            "notes_length": 0,
            "chapters_status": "generated",
            "notes_status": None,
        },
    }
    context.update(overrides)
    return environment.get_template("transcript.html").render(**context)


def test_generated_notes_render_foldable_section_and_exports():
    html = _render_notes_template(
        notes_html='<h2 id="notes-chapter-0">Intro</h2><ul><li>Fact</li></ul>',
        notes_state="generated",
        stats={
            "original_length": 100,
            "calibrated_length": 90,
            "summary_length": 20,
            "notes_length": 50,
            "chapters_status": "generated",
            "notes_status": "generated",
        },
    )

    assert "详细笔记" in html
    assert 'id="notes-content-block"' in html
    assert 'id="notes-chapter-0"' in html
    assert "?raw=notes" in html
    assert "?page=notes" in html
    # The shared controller keeps the action mapping in the page script even
    # when generated notes hide the actual button; assert against rendered DOM
    # markup rather than implementation script identifiers.
    assert 'id="generateNotesBtn" type="button"' not in html


def test_generated_chapters_show_generate_notes_button():
    html = _render_notes_template()

    assert 'id="generateNotesBtn" type="button"' in html
    assert "生成详细笔记" in html
    assert "'generate_notes':" in html
    assert "createProtectedActionController" in html
    assert "fetch('/api/generate_notes'" not in html


def test_failed_notes_show_retry_copy():
    html = _render_notes_template(
        notes_state="failed",
        stats={
            "original_length": 100,
            "calibrated_length": 90,
            "summary_length": 20,
            "notes_length": 0,
            "chapters_status": "generated",
            "notes_status": "failed",
        },
    )

    assert "详细笔记生成失败，可重试" in html


def test_missing_chapters_hide_generate_notes_button():
    html = _render_notes_template(
        stats={
            "original_length": 100,
            "calibrated_length": 90,
            "summary_length": 20,
            "notes_length": 0,
            "chapters_status": "failed",
            "notes_status": None,
        }
    )

    assert 'id="generateNotesBtn"' not in html
