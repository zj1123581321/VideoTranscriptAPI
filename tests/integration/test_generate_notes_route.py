"""Integration tests for the on-demand detailed-notes route.

All console output must stay ASCII-only.
"""

import asyncio
import queue
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from video_transcript_api.api.services.transcription import GenerateNotesRequest
from video_transcript_api.cache.cache_manager import CacheManager
from video_transcript_api.utils.llm_status import ChaptersStatus, NotesStatus


@pytest.fixture
def notes_cache(tmp_path):
    manager = CacheManager(str(tmp_path / "cache"))
    yield manager
    manager.close()


def _seed_notes_source(
    cache_manager,
    *,
    chapters_status=ChaptersStatus.GENERATED,
    notes_status=None,
):
    task = cache_manager.create_task(
        url="https://example.com/notes",
        platform="youtube",
        media_id="notes-media",
        submitted_by="notes-owner",
    )
    cache_manager.save_cache(
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
    cache_manager.save_llm_result(
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
    cache_manager.save_llm_status(
        platform="youtube",
        media_id="notes-media",
        use_speaker_recognition=False,
        chapters_status=chapters_status,
        notes_status=notes_status,
    )
    if notes_status == NotesStatus.GENERATED:
        cache_manager.save_llm_result(
            platform="youtube",
            media_id="notes-media",
            use_speaker_recognition=False,
            llm_type="notes",
            content="existing notes",
        )
    return task


def _configure_notes_route(
    cache_manager,
    monkeypatch,
    *,
    owned=True,
    permission=True,
):
    from video_transcript_api.api.routes import tasks as tasks_route
    import video_transcript_api.api.context as context_module

    llm_queue = queue.Queue(maxsize=10)
    monkeypatch.setattr(context_module, "get_llm_queue", lambda: llm_queue)
    monkeypatch.setattr(
        tasks_route,
        "check_view_token_ownership",
        MagicMock(return_value=owned),
    )

    async def _inline_to_thread(function, *args, **kwargs):
        return function(*args, **kwargs)

    monkeypatch.setattr(tasks_route.asyncio, "to_thread", _inline_to_thread)
    user_manager = MagicMock()
    user_manager.check_permission.return_value = permission
    monkeypatch.setattr(tasks_route, "user_manager", user_manager)
    monkeypatch.setattr(tasks_route, "cache_manager", cache_manager)
    monkeypatch.setattr(tasks_route, "audit_logger", MagicMock())
    return tasks_route, llm_queue


def _call_generate_notes(tasks_route, view_token):
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/generate_notes",
            "headers": [],
            "client": ("127.0.0.1", 12345),
        }
    )
    return asyncio.run(
        tasks_route.generate_notes(
            request_body=GenerateNotesRequest(view_token=view_token),
            request=request,
            user_info={
                "user_id": "notes-owner",
                "api_key": "sk-notes",
                "wechat_webhook": None,
            },
        )
    )


def test_generate_notes_enqueues_notes_only_task(notes_cache, monkeypatch):
    task = _seed_notes_source(notes_cache)
    tasks_route, llm_queue = _configure_notes_route(notes_cache, monkeypatch)

    response = _call_generate_notes(tasks_route, task["view_token"])

    assert response.code == 202
    queued = llm_queue.get_nowait()
    assert queued["processing_options"] == {
        "calibrate": False,
        "summarize": False,
        "infer_speaker_names": False,
        "chapters": False,
        "notes": True,
    }
    assert queued["platform"] == "youtube"
    assert queued["media_id"] == "notes-media"
    assert queued["cache_dir"]

    created = notes_cache.get_task_by_id(response.data["task_id"])
    assert created["submitted_by"] == "notes-owner"
    assert created["processing_options"] == queued["processing_options"]


def test_generate_notes_requires_generated_chapters(notes_cache, monkeypatch):
    task = _seed_notes_source(
        notes_cache,
        chapters_status=ChaptersStatus.FAILED,
    )
    tasks_route, llm_queue = _configure_notes_route(notes_cache, monkeypatch)

    with pytest.raises(HTTPException) as exc_info:
        _call_generate_notes(tasks_route, task["view_token"])

    assert exc_info.value.status_code == 409
    assert "详细笔记依赖已生成的章节层" in exc_info.value.detail
    assert llm_queue.empty()


def test_generate_notes_rejects_generated_notes(notes_cache, monkeypatch):
    task = _seed_notes_source(
        notes_cache,
        notes_status=NotesStatus.GENERATED,
    )
    tasks_route, llm_queue = _configure_notes_route(notes_cache, monkeypatch)

    with pytest.raises(HTTPException) as exc_info:
        _call_generate_notes(tasks_route, task["view_token"])

    assert exc_info.value.status_code == 400
    assert "详细笔记已存在" in exc_info.value.detail
    assert llm_queue.empty()


def test_generate_notes_rejects_cross_user(notes_cache, monkeypatch):
    task = _seed_notes_source(notes_cache)
    tasks_route, llm_queue = _configure_notes_route(
        notes_cache,
        monkeypatch,
        owned=False,
    )

    with pytest.raises(HTTPException) as exc_info:
        _call_generate_notes(tasks_route, task["view_token"])

    assert exc_info.value.status_code == 403
    assert llm_queue.empty()


def test_generate_notes_allows_failed_retry(notes_cache, monkeypatch):
    task = _seed_notes_source(
        notes_cache,
        notes_status=NotesStatus.FAILED,
    )
    tasks_route, llm_queue = _configure_notes_route(notes_cache, monkeypatch)

    response = _call_generate_notes(tasks_route, task["view_token"])

    assert response.code == 202
    assert llm_queue.qsize() == 1
