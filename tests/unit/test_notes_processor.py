"""Unit tests for chapter-detailed notes processing."""

import json
from pathlib import Path
from types import SimpleNamespace

from video_transcript_api.llm.core.config import LLMConfig
from video_transcript_api.llm.processors.notes_processor import (
    NotesProcessor,
    compute_notes_anchor_fingerprint,
    load_notes_source_segments,
)
from video_transcript_api.llm.prompts import (
    NOTES_SYSTEM_PROMPT,
    build_notes_user_prompt,
)
from video_transcript_api.utils.llm_status import NotesStatus


class FakeNotesClient:
    """Record calls and return scripted responses without network access."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def call(self, **kwargs):
        self.calls.append(kwargs)
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


def _config():
    return LLMConfig(
        api_key="test-key",
        base_url="http://localhost",
        calibrate_model="calibrate-model",
        summary_model="summary-model",
        summary_reasoning_effort="low",
        notes_model="notes-model",
        notes_reasoning_effort="high",
    )


def _structured_segments():
    return [
        {
            "start_time": 0,
            "end_time": 5,
            "speaker": "Alice",
            "text": "第一句包含张三和数字 2024。",
        },
        {
            "start_time": 5,
            "end_time": 10,
            "speaker": "Bob",
            "text": "第二句保留原话。",
        },
        {
            "start_time": 10,
            "end_time": 15,
            "speaker": "Cara",
            "text": "第三句属于下一章。",
        },
    ]


def _chapter_payload(segments):
    return {
        "source": {
            "kind": "dialogs",
            "fingerprint": compute_notes_anchor_fingerprint(segments),
        },
        "chapters": [
            {
                "title": "第一章",
                "gist": "开场观点",
                "start_seg": 0,
                "end_seg": 1,
            },
            {
                "title": "第二章",
                "gist": "后续观点",
                "start_seg": 2,
                "end_seg": 2,
            },
        ],
    }


def test_structured_slice_is_closed_and_calls_notes_sequentially():
    segments = _structured_segments()
    client = FakeNotesClient(["- **第一章结论**", "- 第二章结论"])
    processor = NotesProcessor(client, _config())

    result = processor.process(
        chapters=_chapter_payload(segments),
        structured_data={"dialogs": segments},
    )

    assert result.status is NotesStatus.GENERATED
    assert result.error is None
    assert result.text == (
        "## [00:00:00 - 00:00:10] 第一章\n- **第一章结论**\n\n"
        "## [00:00:10 - 00:00:15] 第二章\n- 第二章结论"
    )
    assert len(client.calls) == 2
    assert [call["task_type"] for call in client.calls] == ["notes", "notes"]
    assert all(call["system_prompt"] == NOTES_SYSTEM_PROMPT for call in client.calls)
    assert all(call["model"] == "notes-model" for call in client.calls)
    assert all(call["reasoning_effort"] == "high" for call in client.calls)
    assert "[00:00:00 - 00:00:05] Alice: 第一" in client.calls[0]["user_prompt"]
    assert "[00:00:05 - 00:00:10] Bob: 第二句" in client.calls[0]["user_prompt"]
    assert "Cara: 第三句" not in client.calls[0]["user_prompt"]
    assert "上一章标题：第一章" in client.calls[1]["user_prompt"]
    assert "下一章标题：无" in client.calls[1]["user_prompt"]


def test_plain_source_slice_uses_segments_and_unknown_speaker():
    segments = [
        {"start": 1, "end": 2, "text": "纯文本第一句"},
        {"start": 2, "end": 3, "text": "纯文本第二句"},
    ]
    chapters = {
        "source": {
            "kind": "segments",
            "fingerprint": compute_notes_anchor_fingerprint(segments),
        },
        "chapters": [
            {
                "title": "纯文本章",
                "gist": "纯文本概要",
                "start_seg": 0,
                "end_seg": 1,
            }
        ],
    }
    client = FakeNotesClient([SimpleNamespace(text="- 纯文本笔记")])

    result = NotesProcessor(client, _config()).process(
        chapters=chapters,
        source_segments=segments,
        source_kind="segments",
    )

    assert result.status is NotesStatus.GENERATED
    prompt = client.calls[0]["user_prompt"]
    assert "[00:00:01 - 00:00:02] Unknown: 纯文本第一句" in prompt
    assert "[00:00:02 - 00:00:03] Unknown: 纯文本第二句" in prompt


def test_cache_source_loader_selects_structured_or_plain_path(tmp_path: Path):
    (tmp_path / "llm_processed.json").write_text(
        json.dumps({"dialogs": [{"text": "dialog"}]}), encoding="utf-8"
    )
    (tmp_path / "transcript_capswriter.json").write_text(
        json.dumps({"segments": [{"text": "plain"}]}), encoding="utf-8"
    )

    structured, structured_kind = load_notes_source_segments(tmp_path, "dialogs")
    plain, plain_kind = load_notes_source_segments(tmp_path, "segments")

    assert structured_kind == "dialogs"
    assert structured == [{"text": "dialog"}]
    assert plain_kind == "segments"
    assert plain == [{"start_time": None, "end_time": None, "text": "plain"}]


def test_fingerprint_mismatch_fails_without_llm_call():
    segments = _structured_segments()
    client = FakeNotesClient(["should not be used"])

    result = NotesProcessor(client, _config()).process(
        chapters=_chapter_payload(segments),
        source_segments=segments,
        stored_fingerprint="wrong-fingerprint",
    )

    assert result.status is NotesStatus.FAILED
    assert result.text is None
    assert result.error == "chapter anchor fingerprint mismatch"
    assert result.fingerprint == compute_notes_anchor_fingerprint(segments)
    assert client.calls == []


def test_one_chapter_failure_returns_no_partial_text():
    segments = _structured_segments()
    client = FakeNotesClient(["- first", RuntimeError("provider exploded")])

    result = NotesProcessor(client, _config()).process(
        chapters=_chapter_payload(segments),
        source_segments=segments,
    )

    assert result.status is NotesStatus.FAILED
    assert result.text is None
    assert result.error.startswith("chapter 1 notes generation failed: provider exploded")
    assert len(client.calls) == 2


def test_notes_prompt_contract_contains_context_and_constraints():
    prompt = build_notes_user_prompt(
        chapter_title="本章",
        chapter_gist="本章概要",
        chapter_text="[00:00:01 - 00:00:02] Alice: 原话",
        previous_title="上一章",
        next_title="下一章",
    )

    assert "只输出中文 Markdown" in NOTES_SYSTEM_PROMPT
    assert "分层 bullets" in NOTES_SYSTEM_PROMPT
    assert "人名、数字、时间点" in NOTES_SYSTEM_PROMPT
    assert "不得新增事实" in NOTES_SYSTEM_PROMPT
    assert "使用 Markdown 加粗" in NOTES_SYSTEM_PROMPT
    assert "本章标题：本章" in prompt
    assert "本章概要：本章概要" in prompt
    assert "上一章标题：上一章" in prompt
    assert "下一章标题：下一章" in prompt
    assert "[00:00:01 - 00:00:02] Alice: 原话" in prompt
