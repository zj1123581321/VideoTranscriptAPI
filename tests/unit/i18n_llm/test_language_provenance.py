"""Generation-layer cache reuse is judged by provenance language.

Console output must stay ASCII-only (no emoji).
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from video_transcript_api.api.services import llm_ops
from video_transcript_api.cache.cache_manager import generation_layer_language
from video_transcript_api.utils.logging.logger import load_config


@pytest.fixture
def language_config():
    config = load_config()
    had_key = "language" in config
    original = config.get("language")

    def _set(value):
        if value is None:
            config.pop("language", None)
        else:
            config["language"] = value

    try:
        yield _set
    finally:
        if had_key:
            config["language"] = original
        else:
            config.pop("language", None)


def test_missing_language_field_is_zh_cn():
    assert generation_layer_language(None) == "zh-CN"
    assert generation_layer_language({}) == "zh-CN"
    assert generation_layer_language({"language": ""}) == "zh-CN"
    assert generation_layer_language({"language": "en"}) == "en"


def test_collect_mismatch_treats_legacy_summary_as_zh_cn(tmp_path):
    (tmp_path / "llm_summary.txt").write_text("old chinese summary", encoding="utf-8")
    (tmp_path / "llm_calibrated.txt").write_text("calibrated", encoding="utf-8")

    mismatches = llm_ops.collect_language_mismatched_generation_layers(
        cache_dir=str(tmp_path),
        layers={},
        current_language="en",
    )
    assert ("summary", "zh-CN", "en") in mismatches
    assert all(item[0] != "calibration" for item in mismatches)


def test_matching_language_is_not_a_mismatch(tmp_path):
    (tmp_path / "llm_summary.txt").write_text("english summary", encoding="utf-8")
    mismatches = llm_ops.collect_language_mismatched_generation_layers(
        cache_dir=str(tmp_path),
        layers={"summary": {"language": "en"}},
        current_language="en",
    )
    assert mismatches == []


def test_calibration_layer_is_ignored_even_when_language_differs(tmp_path):
    mismatches = llm_ops.collect_language_mismatched_generation_layers(
        cache_dir=str(tmp_path),
        layers={"calibration": {"language": "zh-CN"}, "summary": {"language": "zh-CN"}},
        current_language="en",
    )
    assert ("calibration", "zh-CN", "en") not in mismatches
    assert ("summary", "zh-CN", "en") in mismatches


def test_language_mismatch_regenerate_log_locked(language_config):
    language_config("en")
    with patch.object(llm_ops, "logger") as mock_logger:
        llm_ops.log_language_mismatch_regenerate("summary", "zh-CN", "en")
    mock_logger.warning.assert_called_once()
    message = mock_logger.warning.call_args[0][0]
    assert message.startswith("LANGUAGE-MISMATCH-REGENERATE")
    assert "layer=summary" in message
    assert "old=zh-CN" in message
    assert "new=en" in message


def test_notes_and_chapters_and_share_card_are_generation_layers(tmp_path):
    (tmp_path / "llm_notes.txt").write_text("notes", encoding="utf-8")
    (tmp_path / "llm_chapters.json").write_text("{}", encoding="utf-8")
    (tmp_path / "llm_share_card.json").write_text("{}", encoding="utf-8")
    mismatches = llm_ops.collect_language_mismatched_generation_layers(
        cache_dir=str(tmp_path),
        layers={
            "notes": {"language": "zh-CN"},
            "chapters": {"language": "zh-CN"},
            "share_card": {"language": "zh-CN"},
        },
        current_language="en",
    )
    names = {item[0] for item in mismatches}
    assert names == {"notes", "chapters", "share_card"}
