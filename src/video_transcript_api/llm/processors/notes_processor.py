"""Chapter-mapped detailed notes generation.

This module owns the source-to-chapter mapping and anchor validation used by
the queue layer.  It deliberately does not write cache files; callers persist
only a successful ``NotesResult`` through ``CacheManager``.
"""

import contextvars
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple, Union

from ...transcriber.segments import load_segments, parse_time_to_seconds
from ...utils.llm_status import NotesStatus
from ..core.config import LLMConfig
from ..core.llm_client import LLMClient
from ..prompts import NOTES_SYSTEM_PROMPT, build_notes_user_prompt
from .chapters_processor import _compute_fingerprint


@dataclass(frozen=True)
class NotesChapterSlice:
    """One chapter's original, closed-range segment slice."""

    index: int
    title: str
    gist: str
    start_seg: int
    end_seg: int
    segments: Tuple[Mapping[str, Any], ...]
    start_time: Optional[float]
    end_time: Optional[float]


@dataclass(frozen=True)
class NotesMappingResult:
    """Validated chapter slices and the fingerprints used for the decision."""

    slices: Tuple[NotesChapterSlice, ...]
    stored_fingerprint: Optional[str]
    current_fingerprint: Optional[str]
    error: Optional[str] = None

    @property
    def is_valid(self) -> bool:
        """Return whether chapter anchors and closed-range slices are usable."""
        return self.error is None and bool(self.slices)


@dataclass(frozen=True)
class NotesResult:
    """Processor result; ``text`` is present only for a complete success."""

    text: Optional[str]
    status: NotesStatus
    error: Optional[str] = None
    fingerprint: Optional[str] = None
    chapter_count: int = 0


def compute_notes_anchor_fingerprint(
    segments: Sequence[Any],
) -> Optional[str]:
    """Compute the same filtered SHA-1 anchor fingerprint as the chapters view."""
    if not segments:
        return None

    filtered_pairs: List[Tuple[int, Dict[str, Any]]] = []
    for original_index, segment in enumerate(segments):
        if not isinstance(segment, dict):
            continue
        text = segment.get("text")
        if not isinstance(text, str) or not text.strip():
            continue
        filtered_pairs.append((original_index, segment))

    if not filtered_pairs:
        return None
    return _compute_fingerprint(filtered_pairs)


def _read_json_file(path: Path) -> Optional[Dict[str, Any]]:
    try:
        with path.open("r", encoding="utf-8") as file:
            value = json.load(file)
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def load_notes_source_segments(
    cache_dir: Union[str, Path],
    source_kind: Optional[str] = None,
) -> Tuple[Optional[List[Dict[str, Any]]], Optional[str]]:
    """Load the chapter anchor source without importing the routes layer.

    ``dialogs``/``cached_dialogs`` sources use ``llm_processed.json``.  A
    ``segments`` source uses the shared ``load_segments`` adapter, preserving
    the plain-text path's normalized list and original index order.
    """
    cache_path = Path(cache_dir)
    normalized_kind = (source_kind or "").lower()
    wants_dialogs = normalized_kind in {
        "dialogs",
        "cached_dialogs",
        "structured",
        "plain_structured",
    }
    wants_segments = normalized_kind in {"segments", "timeline"}

    processed = _read_json_file(cache_path / "llm_processed.json")
    dialogs = processed.get("dialogs") if processed else None
    if (wants_dialogs or not wants_segments) and isinstance(dialogs, list) and dialogs:
        return dialogs, "dialogs"

    segments = load_segments(cache_path)
    if isinstance(segments, list) and segments:
        return segments, "segments"

    if not wants_segments and isinstance(dialogs, list) and dialogs:
        return dialogs, "dialogs"
    return None, None


def _extract_chapter_payload(
    chapters: Union[Mapping[str, Any], Sequence[Mapping[str, Any]]],
) -> Tuple[Optional[List[Mapping[str, Any]]], Optional[str]]:
    if isinstance(chapters, Mapping):
        raw_chapters = chapters.get("chapters")
        source = chapters.get("source")
        stored_fingerprint = source.get("fingerprint") if isinstance(source, Mapping) else None
    else:
        raw_chapters = chapters
        stored_fingerprint = None

    if not isinstance(raw_chapters, list):
        return None, stored_fingerprint
    return raw_chapters, stored_fingerprint


def _segment_time(segment: Mapping[str, Any], field: str) -> Optional[float]:
    value = segment.get(field)
    if value is None and field == "end_time":
        value = segment.get("end")
    if value is None and field == "start_time":
        value = segment.get("start")
    return parse_time_to_seconds(value)


def _chapter_time(
    segments: Sequence[Mapping[str, Any]],
    field: str,
    chapter_value: Any = None,
) -> Optional[float]:
    if segments:
        candidate = _segment_time(segments[0 if field == "start_time" else -1], field)
        if candidate is not None:
            return candidate
    return parse_time_to_seconds(chapter_value)


def map_notes_chapter_slices(
    chapters: Union[Mapping[str, Any], Sequence[Mapping[str, Any]]],
    source_segments: Sequence[Any],
    *,
    stored_fingerprint: Optional[str] = None,
) -> NotesMappingResult:
    """Map ``start_seg``/``end_seg`` as original zero-based closed intervals.

    The stored fingerprint is mandatory for safe reuse.  A missing or changed
    fingerprint is a deterministic failure, so callers cannot create notes
    against shifted chapter anchors.
    """
    raw_chapters, payload_fingerprint = _extract_chapter_payload(chapters)
    expected_fingerprint = stored_fingerprint or payload_fingerprint
    current_fingerprint = compute_notes_anchor_fingerprint(source_segments)

    if not expected_fingerprint or not current_fingerprint:
        return NotesMappingResult(
            slices=(),
            stored_fingerprint=expected_fingerprint,
            current_fingerprint=current_fingerprint,
            error="chapter anchor fingerprint unavailable",
        )
    if expected_fingerprint != current_fingerprint:
        return NotesMappingResult(
            slices=(),
            stored_fingerprint=expected_fingerprint,
            current_fingerprint=current_fingerprint,
            error="chapter anchor fingerprint mismatch",
        )
    if not raw_chapters:
        return NotesMappingResult(
            slices=(),
            stored_fingerprint=expected_fingerprint,
            current_fingerprint=current_fingerprint,
            error="chapters payload is empty",
        )

    mapped: List[NotesChapterSlice] = []
    source_count = len(source_segments)
    for chapter_index, chapter in enumerate(raw_chapters):
        if not isinstance(chapter, Mapping):
            return NotesMappingResult(
                slices=tuple(mapped),
                stored_fingerprint=expected_fingerprint,
                current_fingerprint=current_fingerprint,
                error=f"chapters[{chapter_index}] is not an object",
            )

        start_seg = chapter.get("start_seg")
        end_seg = chapter.get("end_seg")
        if (
            isinstance(start_seg, bool)
            or isinstance(end_seg, bool)
            or not isinstance(start_seg, int)
            or not isinstance(end_seg, int)
        ):
            error = f"chapters[{chapter_index}] has invalid segment bounds"
            return NotesMappingResult(
                slices=tuple(mapped),
                stored_fingerprint=expected_fingerprint,
                current_fingerprint=current_fingerprint,
                error=error,
            )
        if start_seg < 0 or end_seg < start_seg or end_seg >= source_count:
            error = f"chapters[{chapter_index}] segment bounds are outside source"
            return NotesMappingResult(
                slices=tuple(mapped),
                stored_fingerprint=expected_fingerprint,
                current_fingerprint=current_fingerprint,
                error=error,
            )

        title = chapter.get("title")
        gist = chapter.get("gist")
        if not isinstance(title, str) or not title.strip():
            return NotesMappingResult(
                slices=tuple(mapped),
                stored_fingerprint=expected_fingerprint,
                current_fingerprint=current_fingerprint,
                error=f"chapters[{chapter_index}].title is blank",
            )
        if not isinstance(gist, str) or not gist.strip():
            return NotesMappingResult(
                slices=tuple(mapped),
                stored_fingerprint=expected_fingerprint,
                current_fingerprint=current_fingerprint,
                error=f"chapters[{chapter_index}].gist is blank",
            )

        chapter_segments = tuple(
            segment
            for segment in source_segments[start_seg : end_seg + 1]
            if isinstance(segment, Mapping)
        )
        if not chapter_segments:
            return NotesMappingResult(
                slices=tuple(mapped),
                stored_fingerprint=expected_fingerprint,
                current_fingerprint=current_fingerprint,
                error=f"chapters[{chapter_index}] has no usable segments",
            )

        mapped.append(
            NotesChapterSlice(
                index=chapter_index,
                title=title.strip(),
                gist=gist.strip(),
                start_seg=start_seg,
                end_seg=end_seg,
                segments=chapter_segments,
                start_time=_chapter_time(
                    chapter_segments,
                    "start_time",
                    chapter.get("start_time"),
                ),
                end_time=_chapter_time(
                    chapter_segments,
                    "end_time",
                    chapter.get("end_time"),
                ),
            )
        )

    return NotesMappingResult(
        slices=tuple(mapped),
        stored_fingerprint=expected_fingerprint,
        current_fingerprint=current_fingerprint,
    )


def _format_notes_timestamp(seconds: Optional[float]) -> str:
    if seconds is None or not math.isfinite(seconds):
        return ""
    total = max(0, int(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, seconds_value = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds_value:02d}"


def _format_segment_time_range(segment: Mapping[str, Any]) -> str:
    start = _format_notes_timestamp(_segment_time(segment, "start_time"))
    end = _format_notes_timestamp(_segment_time(segment, "end_time"))
    if start and end:
        return f"{start} - {end}"
    return start or end or "time unavailable"


def _segment_speaker(segment: Mapping[str, Any]) -> str:
    for key in ("speaker", "speaker_name", "spk", "speaker_id"):
        value = segment.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return "Unknown"


def format_notes_segment_slice(segments: Sequence[Mapping[str, Any]]) -> str:
    """Render timestamped, speaker-labelled source lines for one chapter."""
    lines = []
    for segment in segments:
        text = segment.get("text")
        if not isinstance(text, str) or not text.strip():
            continue
        lines.append(
            f"[{_format_segment_time_range(segment)}] "
            f"{_segment_speaker(segment)}: {text.strip()}"
        )
    return "\n".join(lines)


def _format_chapter_heading(chapter: NotesChapterSlice) -> str:
    start = _format_notes_timestamp(chapter.start_time)
    end = _format_notes_timestamp(chapter.end_time)
    if start and end:
        return f"## [{start} - {end}] {chapter.title}"
    return f"## {chapter.title}"


class NotesProcessor:
    """Generate detailed notes one chapter at a time without cache writes."""

    def __init__(self, llm_client: LLMClient, config: LLMConfig):
        self.llm_client = llm_client
        self.config = config

    def process(
        self,
        cache_dir: Optional[Union[str, Path]] = None,
        *,
        chapters: Optional[Union[Mapping[str, Any], Sequence[Mapping[str, Any]]]] = None,
        structured_data: Optional[Mapping[str, Any]] = None,
        source_segments: Optional[Sequence[Any]] = None,
        stored_fingerprint: Optional[str] = None,
        source_kind: Optional[str] = None,
        selected_models: Optional[Mapping[str, Any]] = None,
    ) -> NotesResult:
        """Generate all notes or return a deterministic failure with no output."""
        try:
            chapter_payload = chapters
            payload_fingerprint = stored_fingerprint
            if cache_dir is not None:
                chapter_payload = _read_json_file(Path(cache_dir) / "llm_chapters.json")
                if isinstance(chapter_payload, Mapping):
                    source = chapter_payload.get("source")
                    if payload_fingerprint is None and isinstance(source, Mapping):
                        payload_fingerprint = source.get("fingerprint")
                    if source_kind is None and isinstance(source, Mapping):
                        source_kind = source.get("kind")

            if chapter_payload is None:
                return self._failed("llm_chapters.json is missing or invalid")

            if structured_data is not None:
                source = structured_data.get("dialogs")
            elif source_segments is not None:
                source = source_segments
            elif cache_dir is not None:
                source, _ = load_notes_source_segments(cache_dir, source_kind)
            else:
                source = None

            if not isinstance(source, Sequence) or isinstance(source, (str, bytes)):
                return self._failed("chapter anchor source is missing or invalid")

            mapping = map_notes_chapter_slices(
                chapter_payload,
                source,
                stored_fingerprint=payload_fingerprint,
            )
            if not mapping.is_valid:
                return NotesResult(
                    text=None,
                    status=NotesStatus.FAILED,
                    error=mapping.error,
                    fingerprint=mapping.current_fingerprint,
                    chapter_count=len(mapping.slices),
                )

            model, reasoning_effort = self._resolve_model(selected_models)
            def generate_chapter_notes(position: int, chapter: NotesChapterSlice) -> str:
                chapter_text = format_notes_segment_slice(chapter.segments)
                if not chapter_text:
                    raise RuntimeError(
                        f"chapter {position} has no renderable transcript"
                    )

                previous_title = mapping.slices[position - 1].title if position else ""
                next_title = (
                    mapping.slices[position + 1].title
                    if position + 1 < len(mapping.slices)
                    else ""
                )
                user_prompt = build_notes_user_prompt(
                    chapter_title=chapter.title,
                    chapter_gist=chapter.gist,
                    chapter_text=chapter_text,
                    previous_title=previous_title,
                    next_title=next_title,
                )
                try:
                    response = self.llm_client.call(
                        model=model,
                        system_prompt=NOTES_SYSTEM_PROMPT,
                        user_prompt=user_prompt,
                        reasoning_effort=reasoning_effort,
                        task_type="notes",
                    )
                except Exception as exc:  # noqa: BLE001 - preserve processor contract
                    raise RuntimeError(
                        f"chapter {position} notes generation failed: {exc}"
                    ) from exc

                chapter_notes = (
                    response
                    if isinstance(response, str)
                    else getattr(response, "text", "")
                )
                if not isinstance(chapter_notes, str) or not chapter_notes.strip():
                    raise RuntimeError(f"chapter {position} notes response is empty")
                return f"{_format_chapter_heading(chapter)}\n{chapter_notes.strip()}"

            max_workers = min(len(mapping.slices), self.config.notes_concurrency)
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = [
                    executor.submit(
                        contextvars.copy_context().run,
                        generate_chapter_notes,
                        position,
                        chapter,
                    )
                    for position, chapter in enumerate(mapping.slices)
                ]
                notes_sections: List[str] = []
                for future in futures:
                    try:
                        notes_sections.append(future.result())
                    except Exception as exc:  # noqa: BLE001 - preserve processor contract
                        # 整批已一次性提交：首个失败后取消尚未开始的章节，
                        # 否则 shutdown(wait=True) 仍会把排队的章节全部跑完，
                        # 白烧 LLM 配额并把失败反馈拖到整批耗时之后。
                        for pending in futures:
                            pending.cancel()
                        return NotesResult(
                            text=None,
                            status=NotesStatus.FAILED,
                            error=str(exc),
                            fingerprint=mapping.current_fingerprint,
                            chapter_count=len(mapping.slices),
                        )

            return NotesResult(
                text="\n\n".join(notes_sections),
                status=NotesStatus.GENERATED,
                fingerprint=mapping.current_fingerprint,
                chapter_count=len(mapping.slices),
            )
        except Exception as exc:  # noqa: BLE001 - processor returns status, not raises
            return self._failed(f"unexpected notes generation error: {exc}")

    def _resolve_model(
        self,
        selected_models: Optional[Mapping[str, Any]],
    ) -> Tuple[str, Optional[str]]:
        default_model = self.config.notes_model or self.config.summary_model
        default_effort = (
            self.config.notes_reasoning_effort
            if self.config.notes_reasoning_effort is not None
            else self.config.summary_reasoning_effort
        )
        if not selected_models:
            return default_model, default_effort
        return (
            selected_models.get("notes_model", default_model) or default_model,
            selected_models.get("notes_reasoning_effort", default_effort),
        )

    @staticmethod
    def _failed(error: str) -> NotesResult:
        return NotesResult(text=None, status=NotesStatus.FAILED, error=error)


__all__ = [
    "NotesChapterSlice",
    "NotesMappingResult",
    "NotesProcessor",
    "NotesResult",
    "compute_notes_anchor_fingerprint",
    "format_notes_segment_slice",
    "load_notes_source_segments",
    "map_notes_chapter_slices",
]
