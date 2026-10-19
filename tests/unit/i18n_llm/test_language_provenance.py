"""Generation-layer cache reuse is judged by provenance language.

Console output must stay ASCII-only (no emoji).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from video_transcript_api.api.services import llm_ops
from video_transcript_api.cache.cache_manager import (
    generation_layer_language,
    language_mismatched_generation_layers,
)
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


def _cache_data(tmp_path, layers, payload_keys=()):
    data = {
        "file_path": str(tmp_path),
        "llm_status": {
            "artifact_provenance": {
                "schema_version": "artifact-provenance-v1",
                "layers": layers,
            }
        },
    }
    for key in payload_keys:
        data[key] = "present"
    return data


def test_missing_language_field_is_zh_cn():
    assert generation_layer_language(None) == "zh-CN"
    assert generation_layer_language({}) == "zh-CN"
    assert generation_layer_language({"language": ""}) == "zh-CN"
    assert generation_layer_language({"language": "en"}) == "en"


def test_collect_mismatch_treats_legacy_summary_as_zh_cn(tmp_path):
    (tmp_path / "llm_summary.txt").write_text("old chinese summary", encoding="utf-8")
    (tmp_path / "llm_calibrated.txt").write_text("calibrated", encoding="utf-8")

    mismatches = language_mismatched_generation_layers(
        _cache_data(tmp_path, {}, payload_keys=("llm_summary",)),
        current_language="en",
    )
    assert ("summary", "zh-CN", "en") in mismatches
    assert all(item[0] != "calibration" for item in mismatches)


def test_matching_language_is_not_a_mismatch(tmp_path):
    (tmp_path / "llm_summary.txt").write_text("english summary", encoding="utf-8")
    mismatches = language_mismatched_generation_layers(
        _cache_data(
            tmp_path,
            {"summary": {"language": "en"}},
            payload_keys=("llm_summary",),
        ),
        current_language="en",
    )
    assert mismatches == []


def test_calibration_layer_is_ignored_even_when_language_differs(tmp_path):
    mismatches = language_mismatched_generation_layers(
        _cache_data(
            tmp_path,
            {
                "calibration": {"language": "zh-CN"},
                "summary": {"language": "zh-CN"},
            },
        ),
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


def test_english_summary_with_share_card_file_is_not_a_mismatch(
    tmp_path, language_config
):
    """A matching English summary must not be regenerated just because a share card file exists."""
    language_config("en")
    (tmp_path / "llm_summary.txt").write_text("english summary", encoding="utf-8")
    (tmp_path / "llm_share_card.json").write_text("{}", encoding="utf-8")
    cache_data = _cache_data(
        tmp_path,
        {"summary": {"language": "en"}},
        payload_keys=("llm_summary",),
    )
    mismatches = language_mismatched_generation_layers(cache_data)
    assert mismatches == []
    with patch.object(llm_ops, "logger") as mock_logger:
        for layer, old, new in mismatches:
            llm_ops.log_language_mismatch_regenerate(layer, old, new)
    mock_logger.warning.assert_not_called()


def test_notes_and_chapters_are_generation_layers(tmp_path):
    (tmp_path / "llm_notes.txt").write_text("notes", encoding="utf-8")
    (tmp_path / "llm_chapters.json").write_text("{}", encoding="utf-8")
    mismatches = language_mismatched_generation_layers(
        _cache_data(
            tmp_path,
            {
                "notes": {"language": "zh-CN"},
                "chapters": {"language": "zh-CN"},
            },
            payload_keys=("llm_notes", "llm_chapters"),
        ),
        current_language="en",
    )
    names = {item[0] for item in mismatches}
    assert names == {"notes", "chapters"}


def test_resubmit_queues_summary_and_logs_language_mismatch(language_config, monkeypatch):
    """Re-submitting a zh-CN summary under language=en must backfill summary."""
    import video_transcript_api.api.services.transcription as transcription
    from video_transcript_api.utils.llm_status import (
        CalibrationStatus,
        ChaptersStatus,
    )

    language_config("en")

    class DummyQueue:
        def __init__(self):
            self.items = []

        def put(self, item):
            self.items.append(item)

    queue = DummyQueue()
    monkeypatch.setattr(transcription, "llm_task_queue", queue)
    monkeypatch.setattr(
        transcription,
        "create_downloader",
        MagicMock(side_effect=AssertionError("download must not run on cache hit")),
    )

    cache_data = {
        "platform": "youtube",
        "media_id": "abc123",
        "title": "cached title",
        "author": "cached author",
        "description": "cached desc",
        "transcript_type": "capswriter",
        "transcript_data": "RAW uncalibrated transcript",
        "use_speaker_recognition": False,
        "llm_calibrated": "real calibrated text",
        "llm_summary": "cached-zh-summary",
        "llm_status": {
            "calibration_status": CalibrationStatus.FULL,
            "summary_status": "generated",
            "chapters_status": ChaptersStatus.SKIPPED_NO_TIMELINE,
            "artifact_provenance": {
                "schema_version": "artifact-provenance-v1",
                "layers": {"summary": {"language": "zh-CN"}},
            },
        },
        "file_path": "/tmp/unused-cache-dir",
    }

    class DummyCacheManager:
        def get_cache(self, platform, media_id, use_speaker_recognition):
            return cache_data

        def get_task_by_id(self, task_id):
            return None

        def update_task_status(self, *args, **kwargs):
            return True

        def generate_task_id(self):
            return "t"

    monkeypatch.setattr(transcription, "cache_manager", DummyCacheManager())

    result = transcription.process_transcription(
        task_id="t",
        url="https://www.youtube.com/watch?v=abc123",
        use_speaker_recognition=False,
        wechat_webhook=None,
        download_url=None,
        metadata_override=None,
        processing_options={"calibrate": True, "summarize": True, "chapters": True},
    )

    assert result["status"] == "success"
    assert queue.items, "summary language mismatch must re-queue LLM work"
    queued_options = queue.items[0]["processing_options"]
    assert queued_options["summarize"] is True
    assert queued_options["calibrate"] is False

    with patch.object(llm_ops, "logger") as mock_logger:
        for layer, old, new in language_mismatched_generation_layers(cache_data):
            if layer == "summary":
                llm_ops.log_language_mismatch_regenerate(layer, old, new)
    mock_logger.warning.assert_called()
    message = mock_logger.warning.call_args[0][0]
    assert message.startswith("LANGUAGE-MISMATCH-REGENERATE")
    assert "layer=summary" in message


def test_generate_notes_allows_language_mismatch(tmp_path, monkeypatch, language_config):
    """Existing notes in another language must be allowed to regenerate."""
    import asyncio
    import queue as queue_mod

    from fastapi import HTTPException
    from starlette.requests import Request

    from video_transcript_api.api.services.transcription import GenerateNotesRequest
    from video_transcript_api.cache.cache_manager import CacheManager
    from video_transcript_api.utils.llm_status import ChaptersStatus, NotesStatus

    language_config("en")
    manager = CacheManager(str(tmp_path / "cache"))
    try:
        task = manager.create_task(
            url="https://example.com/notes",
            platform="youtube",
            media_id="notes-media",
            submitted_by="notes-owner",
        )
        manager.save_cache(
            platform="youtube",
            url="https://example.com/notes",
            media_id="notes-media",
            use_speaker_recognition=False,
            transcript_data="source transcript",
            transcript_type="capswriter",
            title="Notes demo",
            author="Owner",
            description="Demo description",
        )
        manager.save_llm_result(
            platform="youtube",
            media_id="notes-media",
            use_speaker_recognition=False,
            llm_type="chapters",
            content={
                "format_version": "v1",
                "source": {
                    "kind": "segments",
                    "segment_count": 1,
                    "fingerprint": "fingerprint",
                },
                "chapters": [
                    {
                        "title": "Chapter",
                        "gist": "Gist",
                        "start_seg": 0,
                        "end_seg": 0,
                    }
                ],
            },
        )
        manager.save_llm_result(
            platform="youtube",
            media_id="notes-media",
            use_speaker_recognition=False,
            llm_type="notes",
            content="existing notes",
        )
        manager.save_llm_status(
            platform="youtube",
            media_id="notes-media",
            use_speaker_recognition=False,
            chapters_status=ChaptersStatus.GENERATED,
            notes_status=NotesStatus.GENERATED,
            artifact_provenance={
                "schema_version": "artifact-provenance-v1",
                "layers": {"notes": {"language": "zh-CN"}},
            },
        )

        from video_transcript_api.api.routes import tasks as tasks_route
        import video_transcript_api.api.context as context_module

        llm_queue = queue_mod.Queue(maxsize=10)
        monkeypatch.setattr(context_module, "get_llm_queue", lambda: llm_queue)
        monkeypatch.setattr(
            tasks_route,
            "check_view_token_ownership",
            MagicMock(return_value=True),
        )

        async def _inline_to_thread(function, *args, **kwargs):
            return function(*args, **kwargs)

        monkeypatch.setattr(tasks_route.asyncio, "to_thread", _inline_to_thread)
        user_manager = MagicMock()
        user_manager.check_permission.return_value = True
        monkeypatch.setattr(tasks_route, "user_manager", user_manager)
        monkeypatch.setattr(tasks_route, "cache_manager", manager)
        monkeypatch.setattr(tasks_route, "audit_logger", MagicMock())

        request = Request(
            {
                "type": "http",
                "method": "POST",
                "path": "/api/generate_notes",
                "headers": [],
                "client": ("127.0.0.1", 12345),
            }
        )
        response = asyncio.run(
            tasks_route.generate_notes(
                request_body=GenerateNotesRequest(view_token=task["view_token"]),
                request=request,
                user_info={
                    "user_id": "notes-owner",
                    "api_key": "sk-notes",
                    "wechat_webhook": None,
                },
            )
        )
        assert response.code == 202
        queued = llm_queue.get_nowait()
        assert queued["processing_options"]["notes"] is True

        language_config("zh-CN")
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(
                tasks_route.generate_notes(
                    request_body=GenerateNotesRequest(
                        view_token=task["view_token"]
                    ),
                    request=request,
                    user_info={
                        "user_id": "notes-owner",
                        "api_key": "sk-notes",
                        "wechat_webhook": None,
                    },
                )
            )
        assert exc_info.value.status_code == 400
    finally:
        manager.close()
