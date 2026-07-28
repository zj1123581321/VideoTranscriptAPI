"""Unit tests for cache capability detection."""

from video_transcript_api.cache.cache_analyzer import CacheCapabilityAnalyzer


def test_notes_artifact_is_reported(tmp_path):
    (tmp_path / "transcript_capswriter.txt").write_text("transcript", encoding="utf-8")
    (tmp_path / "llm_notes.txt").write_text("notes", encoding="utf-8")

    capabilities = CacheCapabilityAnalyzer().analyze_cache(str(tmp_path))

    assert capabilities.files_present["notes"] is True
    assert capabilities.primary_engine == "capswriter"
