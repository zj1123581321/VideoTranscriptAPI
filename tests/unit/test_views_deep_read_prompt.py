"""Tests for deep-read prompt presets injected by the success view."""

from unittest.mock import patch

from video_transcript_api.api.routes.views import _prepare_success_view


class TestPrepareSuccessViewDeepReadPrompts:
    def test_injects_configured_deep_read_prompt_presets(self, tmp_path):
        (tmp_path / "transcript_capswriter.txt").write_text(
            "Original transcript", encoding="utf-8"
        )
        (tmp_path / "llm_calibrated.txt").write_text(
            "Calibrated transcript", encoding="utf-8"
        )
        configured_presets = [
            {"label": "Read deeply", "template": "Read the full text at {url}"}
        ]
        view_data = {"cache_dir": str(tmp_path), "summary": None}

        with patch(
            "video_transcript_api.api.routes.views.get_config",
            return_value={"web": {"deep_read_prompts": configured_presets}, "llm": {}},
        ):
            _prepare_success_view(view_data)

        assert view_data["deep_read_prompt_presets"] == configured_presets
