"""Lock Chinese generation prompts and select English ones by language.

Console output must stay ASCII-only (no emoji).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from video_transcript_api.llm.prompts import (
    CHAPTERS_SYSTEM_PROMPT,
    NOTES_SYSTEM_PROMPT_BASE,
    NOTES_SYSTEM_PROMPT_NO_SPEAKER,
    NOTES_SYSTEM_PROMPT_SPEAKER,
    SUMMARY_SYSTEM_PROMPT_MULTI_SPEAKER,
    SUMMARY_SYSTEM_PROMPT_SINGLE_SPEAKER,
    build_chapters_user_prompt,
    build_notes_user_prompt,
    build_summary_user_prompt,
)
from video_transcript_api.llm.prompts import en as en_prompts
from video_transcript_api.llm.prompts.localized import (
    build_chapters_user_prompt as build_chapters_user_prompt_localized,
    build_notes_user_prompt as build_notes_user_prompt_localized,
    build_summary_user_prompt as build_summary_user_prompt_localized,
    chapters_system_prompt,
    length_budget_coefficient,
    notes_system_prompt,
    summary_system_prompt,
)
from video_transcript_api.utils.logging.logger import load_config

PROJECT_ROOT = Path(__file__).resolve().parents[3]
BASE_SHA = "708352f6c8807eb8d7e605539480107727cb2fe1"
CHINESE_PROMPT_MODULE = "src/video_transcript_api/llm/prompts/__init__.py"


@pytest.fixture
def language_config():
    """Mutate the process-wide language key and restore it afterwards."""
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


def _git_show(path: str) -> bytes:
    return subprocess.check_output(
        ["git", "show", f"{BASE_SHA}:{path}"],
        cwd=PROJECT_ROOT,
    )


def test_chinese_prompt_module_matches_base_byte_for_byte():
    """Chinese prompt constants stay in prompts/__init__.py and must not drift."""
    current = (PROJECT_ROOT / CHINESE_PROMPT_MODULE).read_bytes()
    assert current == _git_show(CHINESE_PROMPT_MODULE)


def test_chinese_summary_builder_matches_base_when_language_is_zh_cn(language_config):
    language_config("zh-CN")
    prompt = build_summary_user_prompt(
        transcript="正文样本",
        video_title="标题",
        author="作者",
        description="描述",
        budget_target_min=500,
        budget_target_max=3000,
        budget_hard_cap=4500,
    )
    assert prompt.startswith("**篇幅预算**：总长 500–3000 字，不得超过 4500 字。")
    assert "**内容辅助信息**：" in prompt
    assert "- 标题：标题" in prompt
    assert "**转录文本**：" in prompt
    assert "正文样本" in prompt


def test_chinese_notes_builder_matches_zh_cn_literals(language_config):
    language_config(None)
    prompt = build_notes_user_prompt(
        chapter_title="决策",
        chapter_gist="成本",
        chapter_text="[00:00:01] 正文",
        previous_title="",
        next_title="",
    )
    assert prompt.startswith("请根据以下单章转写内容生成本章精读笔记。")
    assert "本章标题：决策" in prompt
    assert "上一章标题：无" in prompt
    assert "下一章标题：无" in prompt


def test_chinese_chapters_builder_matches_zh_cn_literals(language_config):
    language_config("zh-CN")
    prompt = build_chapters_user_prompt(
        segment_lines="[0] 00:00 text",
        video_title="Title",
        author="Author",
        description="Desc",
        retry_hint="start_seg invalid",
    )
    assert prompt.startswith("**⚠️ 上一次输出有误，请修正**：start_seg invalid")
    assert "**内容辅助信息**：" in prompt
    assert "**编号正文**（请基于以下编号划分章节）：" in prompt


def test_chinese_system_prompts_keep_hard_language_constraints(language_config):
    language_config("zh-CN")
    assert "只能使用中文书写" in SUMMARY_SYSTEM_PROMPT_SINGLE_SPEAKER
    assert "只能使用中文书写" in SUMMARY_SYSTEM_PROMPT_MULTI_SPEAKER
    assert "用中文书写" in NOTES_SYSTEM_PROMPT_BASE
    assert "Speaker[x]" in SUMMARY_SYSTEM_PROMPT_SINGLE_SPEAKER
    assert "不超过 20 个字" in CHAPTERS_SYSTEM_PROMPT
    assert "输入每行格式为 `[时间戳] 说话人: 内容`" in NOTES_SYSTEM_PROMPT_SPEAKER
    assert "不得使用 \"Unknown\"、\"说话人A\"" in NOTES_SYSTEM_PROMPT_NO_SPEAKER


def test_localized_wrappers_match_chinese_builders_under_zh_cn(language_config):
    language_config("zh-CN")
    kwargs = dict(
        transcript="body",
        video_title="T",
        author="A",
        description="D",
        budget_target_min=500,
        budget_target_max=3000,
        budget_hard_cap=4500,
    )
    assert build_summary_user_prompt_localized(**kwargs) == build_summary_user_prompt(**kwargs)
    assert summary_system_prompt(0) == SUMMARY_SYSTEM_PROMPT_SINGLE_SPEAKER
    assert summary_system_prompt(2) == SUMMARY_SYSTEM_PROMPT_MULTI_SPEAKER
    assert notes_system_prompt(has_speaker_labels=True) == NOTES_SYSTEM_PROMPT_SPEAKER
    assert notes_system_prompt(has_speaker_labels=False) == NOTES_SYSTEM_PROMPT_NO_SPEAKER
    assert chapters_system_prompt() == CHAPTERS_SYSTEM_PROMPT
    notes_kwargs = dict(
        chapter_title="t",
        chapter_gist="g",
        chapter_text="x",
        previous_title="",
        next_title="",
    )
    assert build_notes_user_prompt_localized(**notes_kwargs) == build_notes_user_prompt(
        **notes_kwargs
    )
    chapters_kwargs = dict(
        segment_lines="[0] 00:00 x",
        video_title="T",
        author="A",
        description="D",
        retry_hint="err",
    )
    assert build_chapters_user_prompt_localized(**chapters_kwargs) == build_chapters_user_prompt(
        **chapters_kwargs
    )
    assert length_budget_coefficient() == 1.0


def test_english_prompts_are_native_not_chinese_plus_write_in_english(language_config):
    language_config("en")
    single = summary_system_prompt(0)
    multi = summary_system_prompt(2)
    notes_speaker = notes_system_prompt(has_speaker_labels=True)
    notes_plain = notes_system_prompt(has_speaker_labels=False)
    chapters = chapters_system_prompt()

    assert single == en_prompts.SUMMARY_SYSTEM_PROMPT_SINGLE_SPEAKER
    assert multi == en_prompts.SUMMARY_SYSTEM_PROMPT_MULTI_SPEAKER
    assert notes_speaker == en_prompts.NOTES_SYSTEM_PROMPT_SPEAKER
    assert notes_plain == en_prompts.NOTES_SYSTEM_PROMPT_NO_SPEAKER
    assert chapters == en_prompts.CHAPTERS_SYSTEM_PROMPT

    for prompt in (single, multi, notes_speaker, notes_plain, chapters):
        assert "只能使用中文书写" not in prompt
        assert "write in English" not in prompt.lower() or "Write in English only" in prompt
        assert "You are" in prompt or "You are the" in prompt or "close-reading" in prompt

    assert "Write in English only" in single
    assert "Speaker N" in single
    assert "Speaker[x]" not in single
    assert "at most 12 words" in chapters
    assert "不超过 20 个字" not in chapters
    assert length_budget_coefficient() == 1.8
    assert en_prompts.LENGTH_BUDGET_COEFFICIENT == 1.8


def test_english_builders_use_english_labels(language_config):
    language_config("en")
    summary = build_summary_user_prompt_localized(
        transcript="hello",
        video_title="Title",
        author="Author",
        description="Desc",
        budget_target_min=900,
        budget_target_max=5400,
        budget_hard_cap=8100,
    )
    assert summary.startswith(
        "**Length budget**: 900–5400 characters total, must not exceed 8100 characters."
    )
    assert "**篇幅预算**" not in summary
    assert "**Transcript**:" in summary

    notes = build_notes_user_prompt_localized(
        chapter_title="Cost",
        chapter_gist="savings",
        chapter_text="[00:00:01] body",
        previous_title="",
        next_title="",
    )
    assert notes.startswith(
        "Please write close-reading notes for this chapter from the transcript slice below."
    )
    assert "Previous chapter title: None" in notes
    assert "上一章标题：无" not in notes

    chapters = build_chapters_user_prompt_localized(
        segment_lines="[0] 00:00 text",
        video_title="Title",
        retry_hint="start_seg invalid",
    )
    assert chapters.startswith(
        "**Previous output was invalid, please fix**: start_seg invalid"
    )
    assert "**⚠️ 上一次输出有误，请修正**" not in chapters
