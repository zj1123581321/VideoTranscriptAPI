"""Select generation prompts by the global ``language`` config.

Chinese prompt text stays in ``prompts/__init__.py`` (byte-locked to C3
base). English text lives in ``prompts/en.py``. Calibration prompts are
not selected here; they still follow detected content language.
"""

from typing import Optional

from ...i18n import get_language
from . import (
    CHAPTERS_SYSTEM_PROMPT as CHAPTERS_SYSTEM_PROMPT_ZH,
    NOTES_SYSTEM_PROMPT_NO_SPEAKER as NOTES_SYSTEM_PROMPT_NO_SPEAKER_ZH,
    NOTES_SYSTEM_PROMPT_SPEAKER as NOTES_SYSTEM_PROMPT_SPEAKER_ZH,
    SUMMARY_SYSTEM_PROMPT_MULTI_SPEAKER as SUMMARY_SYSTEM_PROMPT_MULTI_SPEAKER_ZH,
    SUMMARY_SYSTEM_PROMPT_SINGLE_SPEAKER as SUMMARY_SYSTEM_PROMPT_SINGLE_SPEAKER_ZH,
    build_chapters_user_prompt as build_chapters_user_prompt_zh,
    build_notes_user_prompt as build_notes_user_prompt_zh,
    build_summary_user_prompt as build_summary_user_prompt_zh,
)
from . import en

_CHAPTER_TITLE_MAX_CHARS_ZH = 24
_CHAPTER_TITLE_TRUNCATE_TO_ZH = 23


def is_english() -> bool:
    """Return True when the global output language is English."""
    return get_language() == "en"


def length_budget_coefficient() -> float:
    """Return the length-budget multiplier for the current output language."""
    if is_english():
        return en.LENGTH_BUDGET_COEFFICIENT
    return 1.0


def summary_system_prompt(speaker_count: int) -> str:
    """Return the summary system prompt for the current language."""
    if is_english():
        if speaker_count >= 2:
            return en.SUMMARY_SYSTEM_PROMPT_MULTI_SPEAKER
        return en.SUMMARY_SYSTEM_PROMPT_SINGLE_SPEAKER
    if speaker_count >= 2:
        return SUMMARY_SYSTEM_PROMPT_MULTI_SPEAKER_ZH
    return SUMMARY_SYSTEM_PROMPT_SINGLE_SPEAKER_ZH


def build_summary_user_prompt(
    transcript: str,
    video_title: str = "",
    author: str = "",
    description: str = "",
    budget_target_min: Optional[int] = None,
    budget_target_max: Optional[int] = None,
    budget_hard_cap: Optional[int] = None,
) -> str:
    """Build the summary user prompt in the current output language."""
    builder = en.build_summary_user_prompt if is_english() else build_summary_user_prompt_zh
    return builder(
        transcript=transcript,
        video_title=video_title,
        author=author,
        description=description,
        budget_target_min=budget_target_min,
        budget_target_max=budget_target_max,
        budget_hard_cap=budget_hard_cap,
    )


def notes_system_prompt(*, has_speaker_labels: bool) -> str:
    """Return the notes system prompt for the current language."""
    if is_english():
        if has_speaker_labels:
            return en.NOTES_SYSTEM_PROMPT_SPEAKER
        return en.NOTES_SYSTEM_PROMPT_NO_SPEAKER
    if has_speaker_labels:
        return NOTES_SYSTEM_PROMPT_SPEAKER_ZH
    return NOTES_SYSTEM_PROMPT_NO_SPEAKER_ZH


def build_notes_user_prompt(
    chapter_title: str,
    chapter_gist: str,
    chapter_text: str,
    previous_title: str = "",
    next_title: str = "",
) -> str:
    """Build the notes user prompt in the current output language."""
    builder = en.build_notes_user_prompt if is_english() else build_notes_user_prompt_zh
    return builder(
        chapter_title=chapter_title,
        chapter_gist=chapter_gist,
        chapter_text=chapter_text,
        previous_title=previous_title,
        next_title=next_title,
    )


def chapters_system_prompt() -> str:
    """Return the chapters system prompt for the current language."""
    if is_english():
        return en.CHAPTERS_SYSTEM_PROMPT
    return CHAPTERS_SYSTEM_PROMPT_ZH


def build_chapters_user_prompt(
    segment_lines: str,
    video_title: str = "",
    author: str = "",
    description: str = "",
    retry_hint: str = "",
) -> str:
    """Build the chapters user prompt in the current output language."""
    builder = en.build_chapters_user_prompt if is_english() else build_chapters_user_prompt_zh
    return builder(
        segment_lines=segment_lines,
        video_title=video_title,
        author=author,
        description=description,
        retry_hint=retry_hint,
    )


def chapter_title_limits() -> tuple[int, int]:
    """Return ``(max_chars, truncate_to)`` for chapter titles in the current language."""
    if is_english():
        return en.CHAPTER_TITLE_MAX_CHARS, en.CHAPTER_TITLE_TRUNCATE_TO
    return _CHAPTER_TITLE_MAX_CHARS_ZH, _CHAPTER_TITLE_TRUNCATE_TO_ZH
