"""Tests for configurable deep-read prompt presets."""

from unittest.mock import MagicMock

from video_transcript_api.api.context import get_deep_read_prompt_presets
from video_transcript_api.i18n import ui_language_scope


class TestDeepReadPromptPresets:
    def test_missing_configuration_returns_default_preset(self):
        presets = get_deep_read_prompt_presets({"web": {}})

        assert len(presets) == 1
        assert presets[0]["label"] == "复制深度阅读 Prompt"
        assert presets[0]["builtin"] is True
        assert presets[0]["template"] == (
            "请读取下面 URL 的播客校对稿全文，按时间顺序分主题做详细笔记，保留人名、数字、时间点和原话，"
            "使用分层 bullets，关键论断加粗；不要浓缩省略。\n\n{url}\n"
        )

    def test_builtin_prompt_uses_site_language_outside_visitor_ui_scope(self, monkeypatch):
        import video_transcript_api.api.context as context

        monkeypatch.setattr(context, "get_language", lambda: "en")
        with ui_language_scope("zh-CN"):
            preset = get_deep_read_prompt_presets({"web": {}})[0]

        assert preset["builtin"] is True
        assert preset["label"] == "Copy deep-read prompt"
        assert preset["template"] == (
            "Read the full proofread podcast transcript at the URL below. Create detailed notes "
            "organized by topic in chronological order. Preserve names, numbers, timestamps, "
            "and direct quotes. Use nested bullet points and bold key claims. Do not summarize "
            "or omit details.\n\n{url}\n"
        )

    def test_invalid_items_are_skipped_and_valid_items_are_kept(self):
        warning_logger = MagicMock()
        presets = get_deep_read_prompt_presets(
            {
                "web": {
                    "deep_read_prompts": [
                        {},
                        {"label": "Missing template"},
                        {"template": "Missing label"},
                        {"label": "Missing URL", "template": "Read this"},
                        {"label": "Valid preset", "template": "Read {url}"},
                    ]
                }
            },
            warning_logger=warning_logger,
        )

        assert presets == [{"label": "Valid preset", "template": "Read {url}"}]
        warning_logger.warning.assert_any_call(
            "Invalid deep_read_prompt preset skipped: label and template must be non-empty strings"
        )
        warning_logger.warning.assert_any_call(
            "Invalid deep_read_prompt preset skipped: template must contain {url}"
        )

    def test_all_invalid_items_fall_back_to_default(self):
        warning_logger = MagicMock()
        presets = get_deep_read_prompt_presets(
            {
                "web": {
                    "deep_read_prompts": [
                        {"label": "No URL", "template": "Read this"},
                    ]
                }
            },
            warning_logger=warning_logger,
        )

        assert presets[0]["label"] == "复制深度阅读 Prompt"
        warning_logger.warning.assert_any_call(
            "No valid deep_read_prompt presets configured; using default deep_read_prompt preset"
        )

    def test_non_list_configuration_warns_and_falls_back_to_default(self):
        warning_logger = MagicMock()
        presets = get_deep_read_prompt_presets(
            {"web": {"deep_read_prompts": "not-a-list"}},
            warning_logger=warning_logger,
        )

        assert presets[0]["label"] == "复制深度阅读 Prompt"
        warning_logger.warning.assert_called_once_with(
            "Invalid deep_read_prompt configuration skipped: deep_read_prompts must be an array"
        )

    def test_valid_configuration_uses_default_logger_when_not_provided(self):
        presets = get_deep_read_prompt_presets(
            {
                "web": {
                    "deep_read_prompts": [
                        {"label": "Read deeply", "template": "Read {url}"}
                    ]
                }
            }
        )

        assert presets == [{"label": "Read deeply", "template": "Read {url}"}]
