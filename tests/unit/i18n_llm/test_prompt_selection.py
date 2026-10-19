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
