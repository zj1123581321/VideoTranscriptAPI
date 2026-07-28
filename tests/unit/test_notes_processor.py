"""Unit tests for chapter-detailed notes processing."""

import json
import threading
from pathlib import Path
from types import SimpleNamespace

from video_transcript_api.llm.core.config import LLMConfig
from video_transcript_api.llm.core.usage_context import get_context, set_context
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


def _config(*, notes_concurrency=10):
    return LLMConfig(
        api_key="test-key",
        base_url="http://localhost",
        calibrate_model="calibrate-model",
        summary_model="summary-model",
        summary_reasoning_effort="low",
        notes_model="notes-model",
        notes_reasoning_effort="high",
        notes_concurrency=notes_concurrency,
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


def _chapter_batch(count):
    segments = [
        {
            "start_time": index * 10,
            "end_time": index * 10 + 10,
            "speaker": "Speaker",
            "text": f"Chapter {index} source text",
        }
        for index in range(count)
    ]
    return segments, {
        "source": {
            "kind": "dialogs",
            "fingerprint": compute_notes_anchor_fingerprint(segments),
        },
        "chapters": [
            {
                "title": f"Chapter {index}",
                "gist": f"Chapter {index} gist",
                "start_seg": index,
                "end_seg": index,
            }
            for index in range(count)
        ],
    }


def _chapter_title(user_prompt):
    marker = "本章标题："
    start = user_prompt.index(marker) + len(marker)
    return user_prompt[start:].splitlines()[0]


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


def test_notes_concurrency_keeps_chapter_order_when_completion_is_out_of_order():
    segments, chapters = _chapter_batch(4)
    completed = []
    completion_events = [threading.Event() for _ in range(4)]

    class ReverseCompletionNotesClient:
        def call(self, **kwargs):
            title = _chapter_title(kwargs["user_prompt"])
            chapter_index = int(title.rsplit(" ", 1)[1])
            if chapter_index + 1 < len(completion_events):
                assert completion_events[chapter_index + 1].wait(timeout=5), (
                    f"Timed out waiting for Chapter {chapter_index + 1}"
                )
            completed.append(title)
            completion_events[chapter_index].set()
            return f"- {title} notes"

    result = NotesProcessor(
        ReverseCompletionNotesClient(), _config(notes_concurrency=4)
    ).process(chapters=chapters, source_segments=segments)

    assert result.status is NotesStatus.GENERATED
    assert completed == ["Chapter 3", "Chapter 2", "Chapter 1", "Chapter 0"]
    assert result.text.index("Chapter 0\n- Chapter 0 notes") < result.text.index(
        "Chapter 1\n- Chapter 1 notes"
    )
    assert result.text.index("Chapter 1\n- Chapter 1 notes") < result.text.index(
        "Chapter 2\n- Chapter 2 notes"
    )
    assert result.text.index("Chapter 2\n- Chapter 2 notes") < result.text.index(
        "Chapter 3\n- Chapter 3 notes"
    )


def test_notes_concurrency_does_not_exceed_configured_worker_limit():
    notes_concurrency = 2
    segments, chapters = _chapter_batch(4)
    expected_concurrency = min(len(chapters["chapters"]), notes_concurrency)
    concurrent_barrier = threading.Barrier(expected_concurrency, timeout=5)
    active = 0
    peak = 0
    counter_lock = threading.Lock()

    class CountingNotesClient:
        def call(self, **kwargs):
            nonlocal active, peak
            with counter_lock:
                active += 1
                peak = max(peak, active)
            try:
                concurrent_barrier.wait()
                return "- notes"
            finally:
                with counter_lock:
                    active -= 1

    result = NotesProcessor(
        CountingNotesClient(), _config(notes_concurrency=notes_concurrency)
    ).process(chapters=chapters, source_segments=segments)

    assert result.status is NotesStatus.GENERATED
    assert peak <= notes_concurrency
    assert peak == expected_concurrency


def test_notes_concurrency_propagates_usage_context_to_workers():
    segments, chapters = _chapter_batch(3)
    seen_contexts = []
    context_lock = threading.Lock()

    class ContextNotesClient:
        def call(self, **kwargs):
            with context_lock:
                seen_contexts.append(get_context())
            return "- notes"

    with set_context(task_id="task-123", stage="notes"):
        result = NotesProcessor(ContextNotesClient(), _config(notes_concurrency=3)).process(
            chapters=chapters,
            source_segments=segments,
        )

    assert result.status is NotesStatus.GENERATED
    assert seen_contexts == [
        {"task_id": "task-123", "stage": "notes"},
        {"task_id": "task-123", "stage": "notes"},
        {"task_id": "task-123", "stage": "notes"},
    ]


def test_empty_chapter_response_returns_failed_without_partial_text():
    segments, chapters = _chapter_batch(2)

    class EmptySecondNotesClient:
        def call(self, **kwargs):
            return "" if _chapter_title(kwargs["user_prompt"]) == "Chapter 1" else "- first"

    result = NotesProcessor(EmptySecondNotesClient(), _config(notes_concurrency=2)).process(
        chapters=chapters,
        source_segments=segments,
    )

    assert result.status is NotesStatus.FAILED
    assert result.text is None
    assert result.error == "chapter 1 notes response is empty"


def test_failed_chapter_cancels_queued_chapters_instead_of_burning_quota():
    """Serialized case: a first-chapter failure must not spend calls on queued chapters.

    Cancellation is best-effort in general (idle workers race to pull the next
    queued item); this locks the deterministic single-worker case only.
    """
    segments, chapters = _chapter_batch(5)
    calls = []

    class FailFirstNotesClient:
        def call(self, **kwargs):
            title = _chapter_title(kwargs["user_prompt"])
            calls.append(title)
            if title == "Chapter 0":
                raise RuntimeError("provider exploded")
            return f"- {title} notes"

    # notes_concurrency=1 makes scheduling deterministic: chapters 1..4 are still
    # queued when chapter 0 fails, so they must be cancelled, not executed.
    result = NotesProcessor(FailFirstNotesClient(), _config(notes_concurrency=1)).process(
        chapters=chapters,
        source_segments=segments,
    )

    assert result.status is NotesStatus.FAILED
    assert result.text is None
    assert calls == ["Chapter 0"]


def test_notes_concurrency_config_defaults_to_ten_and_parses_explicit_value():
    base = {
        "api_key": "k",
        "base_url": "u",
        "calibrate_model": "calibrate",
        "summary_model": "summary",
    }

    default_config = LLMConfig.from_dict({"llm": base})
    explicit_config = LLMConfig.from_dict(
        {"llm": {**base, "notes_concurrency": 3}}
    )

    assert default_config.notes_concurrency == 10
    assert explicit_config.notes_concurrency == 3


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
