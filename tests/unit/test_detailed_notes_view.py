"""View preparation and template tests for detailed notes.

All console output must stay ASCII-only.
"""

import json
from pathlib import Path
from unittest.mock import patch

import jinja2

from video_transcript_api.api.routes.views import _prepare_success_view


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
    assert 'id="notes-chapter-1"' in view_data["notes_html"]
    assert 'id="notes-chapter-2"' in view_data["notes_html"]
    assert 'id="intro"' not in view_data["notes_html"]
    assert 'id="detail"' not in view_data["notes_html"]
    assert "<strong>Key claim</strong>" in view_data["notes_html"]


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
        notes_html='<h2 id="notes-chapter-1">Intro</h2><ul><li>Fact</li></ul>',
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
    assert 'id="notes-chapter-1"' in html
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
