"""Unit tests for ShareCardProcessor (og share-card copy, card A).

Covers the llm_share_card.json contract shape, contract rejections
(too-long / empty fields), exception isolation, and share_card_model
selection (explicit / summary fallback / selected_models override).
All LLM calls are mocked; no real request is ever sent.

Console output must be English only.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import Mock

import pytest

from video_transcript_api.llm.core.config import LLMConfig
from video_transcript_api.llm.processors.share_card_processor import (
    ShareCardProcessor,
    ShareCardResult,
    _effective_length,
    _validate_card,
)

CONFIG_DICT = {
    "llm": {
        "api_key": "test_key",
        "base_url": "http://test.api.com",
        "calibrate_model": "test-model",
        "summary_model": "test-summary-model",
        "summary_reasoning_effort": "low",
        "min_summary_threshold": 500,
    }
}


def _make_processor(extra_llm: dict | None = None) -> tuple[ShareCardProcessor, Mock]:
    llm_client = Mock()
    llm_section = dict(CONFIG_DICT["llm"])
    if extra_llm:
        llm_section.update(extra_llm)
    processor = ShareCardProcessor(
        llm_client=llm_client,
        config=LLMConfig.from_dict({"llm": llm_section}),
    )
    return processor, llm_client


def _structured_response(data) -> Mock:
    response = Mock()
    response.structured_output = data
    response.text = ""
    return response


VALID_CARD_DATA = {
    "headline": "三分钟看懂大模型如何改变工作流",
    "points": ["要点一：效率提升十倍", "要点二：成本减半", "要点三：人人可用"],
}


class TestContractShape:
    def test_valid_input_produces_contract_card(self):
        """Successful round must return exactly the contract fields with
        version=1, non-empty headline/points and a tz-aware ISO8601 stamp."""
        processor, llm_client = _make_processor()
        llm_client.call.return_value = _structured_response(dict(VALID_CARD_DATA))

        result = processor.process(
            summary_text="总结正文" * 50,
            title="Video Title",
            author="Channel",
            platform="youtube",
        )

        assert isinstance(result, ShareCardResult)
        assert result.error is None
        card = result.card
        assert set(card.keys()) == {"version", "headline", "points", "generated_at"}
        assert card["version"] == 1
        assert card["headline"] == VALID_CARD_DATA["headline"]
        assert card["points"] == VALID_CARD_DATA["points"]
        # generated_at must parse as tz-aware ISO8601.
        parsed = datetime.fromisoformat(card["generated_at"])
        assert parsed.tzinfo is not None

    def test_uses_summary_model_and_schema(self):
        """Unconfigured share_card_model must fall back to summary_model
        and still pass the share-card response schema."""
        processor, llm_client = _make_processor()
        llm_client.call.return_value = _structured_response(dict(VALID_CARD_DATA))

        processor.process(summary_text="总结正文" * 50, title="T")

        kwargs = llm_client.call.call_args.kwargs
        assert kwargs["model"] == "test-summary-model"
        assert kwargs["reasoning_effort"] == "low"
        assert kwargs["task_type"] == "share_card"
        assert kwargs["response_schema"] is not None
        assert "headline" in kwargs["response_schema"]["properties"]

    def test_explicit_share_card_model_is_used(self):
        """Configured share_card_model / effort must reach llm_client.call."""
        processor, llm_client = _make_processor(
            {
                "share_card_model": "flash-card-model",
                "share_card_reasoning_effort": "disabled",
            }
        )
        llm_client.call.return_value = _structured_response(dict(VALID_CARD_DATA))

        processor.process(summary_text="总结正文" * 50, title="T")

        kwargs = llm_client.call.call_args.kwargs
        assert kwargs["model"] == "flash-card-model"
        assert kwargs["reasoning_effort"] == "disabled"

    def test_selected_models_override_wins(self):
        """selected_models share_card_* keys take priority over config."""
        processor, llm_client = _make_processor(
            {
                "share_card_model": "flash-card-model",
                "share_card_reasoning_effort": "disabled",
            }
        )
        llm_client.call.return_value = _structured_response(dict(VALID_CARD_DATA))

        processor.process(
            summary_text="总结正文" * 50,
            title="T",
            selected_models={
                "share_card_model": "override-card-model",
                "share_card_reasoning_effort": "high",
                "summary_model": "must-not-use-summary-key",
                "summary_reasoning_effort": "medium",
            },
        )

        kwargs = llm_client.call.call_args.kwargs
        assert kwargs["model"] == "override-card-model"
        assert kwargs["reasoning_effort"] == "high"

    def test_long_summary_input_is_truncated(self):
        """Summary body longer than the input cap must be truncated before
        being embedded into the user prompt."""
        processor, llm_client = _make_processor()
        llm_client.call.return_value = _structured_response(dict(VALID_CARD_DATA))

        processor.process(summary_text="字" * 9999, title="T")

        user_prompt = llm_client.call.call_args.kwargs["user_prompt"]
        assert "(truncated)" in user_prompt
        assert "字" * 9999 not in user_prompt


class TestContractRejections:
    @pytest.mark.parametrize(
        "data,reason_fragment",
        [
            ({"headline": "", "points": ["p"]}, "headline"),
            ({"headline": "   ", "points": ["p"]}, "headline"),
            ({"points": ["p"]}, "headline"),
            (
                {"headline": "标" * 31, "points": ["p"]},
                "headline too long",
            ),
            (
                {"headline": "x" * 61, "points": ["p"]},
                "headline too long",
            ),
            ({"headline": "h"}, "points"),
            ({"headline": "h", "points": []}, "points"),
            ({"headline": "h", "points": ["a", "b", "c", "d"]}, "points"),
            ({"headline": "h", "points": [""]}, "points[0]"),
            ({"headline": "h", "points": ["要点" * 21]}, "points[0] too long"),
            ({"headline": "h", "points": ["y" * 81]}, "points[0] too long"),
            ({"headline": "h", "points": ["ok", None]}, "points[1]"),
        ],
    )
    def test_invalid_model_output_is_rejected(self, data, reason_fragment):
        """Out-of-contract model output must produce card=None with a reason,
        never a written card."""
        processor, llm_client = _make_processor()
        llm_client.call.return_value = _structured_response(data)

        result = processor.process(summary_text="总结正文" * 50, title="T")

        assert result.card is None
        assert reason_fragment in result.error

    def test_boundary_lengths_are_accepted(self):
        """Exactly-at-limit fields (30 CJK headline, 40 CJK point, 60-char
        ASCII headline, 80-char ASCII point) must pass."""
        assert _validate_card(
            {"headline": "标" * 30, "points": ["要" * 40, "y" * 80]}
        ) is None
        assert _validate_card({"headline": "x" * 60, "points": ["p"]}) is None

    def test_effective_length_counts_cjk_double(self):
        """CJK chars cost 1 unit, other chars cost 0.5 (contract wording:
        30 汉字 == 60 英文字符)."""
        assert _effective_length("标" * 30) == 30.0
        assert _effective_length("x" * 60) == 30.0

    def test_non_dict_structured_output_is_rejected(self):
        processor, llm_client = _make_processor()
        llm_client.call.return_value = _structured_response("not a dict")

        result = processor.process(summary_text="总结正文" * 50, title="T")

        assert result.card is None
        assert "not a dict" in result.error


class TestExceptionIsolation:
    def test_llm_exception_is_caught_not_raised(self):
        """Any LLM failure must be converted into card=None + error reason;
        it must never propagate to the caller (task must stay successful)."""
        processor, llm_client = _make_processor()
        llm_client.call.side_effect = RuntimeError("boom from provider")

        result = processor.process(summary_text="总结正文" * 50, title="T")

        assert isinstance(result, ShareCardResult)
        assert result.card is None
        assert "RuntimeError" in result.error
        assert "boom from provider" in result.error

    def test_empty_summary_short_circuits_without_llm_call(self):
        processor, llm_client = _make_processor()

        result = processor.process(summary_text="   ", title="T")

        assert result.card is None
        assert result.error == "empty summary text"
        llm_client.call.assert_not_called()
