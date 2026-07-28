"""Unit tests for the export-file-path resolution helper in views.

All console output must be in English only (no emoji, no Chinese).
"""

from pathlib import Path

from video_transcript_api.api.routes.views import (
    generate_download_filename,
    handle_page_export,
    handle_raw_export,
    resolve_export_file_path,
)


class TestResolveExportFilePath:
    def test_calibrated(self, tmp_path):
        p = resolve_export_file_path(str(tmp_path), "calibrated")
        assert p == tmp_path / "llm_calibrated.txt"

    def test_summary(self, tmp_path):
        p = resolve_export_file_path(str(tmp_path), "summary")
        assert p == tmp_path / "llm_summary.txt"

    def test_notes(self, tmp_path):
        p = resolve_export_file_path(str(tmp_path), "notes")
        assert p == tmp_path / "llm_notes.txt"

    def test_transcript_prefers_funasr_when_present(self, tmp_path):
        (tmp_path / "transcript_funasr.json").write_text("{}", encoding="utf-8")
        p = resolve_export_file_path(str(tmp_path), "transcript")
        assert p == tmp_path / "transcript_funasr.json"

    def test_transcript_falls_back_to_capswriter(self, tmp_path):
        # No funasr file present -> capswriter path (even if it doesn't exist yet).
        p = resolve_export_file_path(str(tmp_path), "transcript")
        assert p == tmp_path / "transcript_capswriter.txt"

    def test_unsupported_returns_none(self, tmp_path):
        assert resolve_export_file_path(str(tmp_path), "bogus") is None


def test_raw_notes_export_includes_notes_metadata(tmp_path):
    (tmp_path / "llm_notes.txt").write_text(
        "## Chapter\n- Detailed note.",
        encoding="utf-8",
    )
    response = handle_raw_export(
        {
            "status": "success",
            "cache_dir": str(tmp_path),
            "title": "Demo",
            "platform": "youtube",
            "url": "https://example.com/demo",
            "view_token": "view-notes",
            "notes_state": "generated",
        },
        "notes",
    )

    body = response.body.decode("utf-8")
    assert response.status_code == 200
    assert "Type: 详细笔记" in body
    assert "## Chapter" in body
    assert response.headers["x-content-type"] == "notes"


def test_notes_download_filename_uses_notes_label():
    assert (
        generate_download_filename("Demo", "youtube", "notes")
        == "Demo-详细笔记-YouTube.txt"
    )


def test_page_notes_export_renders_notes_content(tmp_path):
    (tmp_path / "llm_notes.txt").write_text(
        "## Chapter\n- Detailed note.",
        encoding="utf-8",
    )
    response = handle_page_export(
        {
            "status": "success",
            "cache_dir": str(tmp_path),
            "title": "Demo",
            "platform": "youtube",
            "url": "https://example.com/demo",
            "view_token": "view-notes",
            "notes_state": "generated",
        },
        "notes",
    )

    body = response.body.decode("utf-8")
    assert response.status_code == 200
    assert "<title>Demo - 详细笔记</title>" in body
    assert '<h2 id="chapter">Chapter</h2>' in body
    assert "<li>Detailed note.</li>" in body


def test_notes_export_hides_artifact_without_generated_status(tmp_path):
    (tmp_path / "llm_notes.txt").write_text(
        "orphan notes artifact",
        encoding="utf-8",
    )
    response = handle_raw_export(
        {
            "status": "success",
            "cache_dir": str(tmp_path),
            "title": "Demo",
            "platform": "youtube",
            "view_token": "view-notes",
            "notes_state": "failed",
        },
        "notes",
    )

    assert response.status_code == 404
    assert "orphan notes artifact" not in response.body.decode("utf-8")
