"""Increment 2 semantic contradiction scanner tests."""

import logging
from unittest.mock import MagicMock, patch
import json
from pathlib import Path

import pytest

from video_transcript_api.llm.core.config import LLMConfig
from video_transcript_api.llm.core.contradiction_scanner import (
    ContradictionScanner,
    MAX_SCAN_SEGMENTS,
)
from video_transcript_api.llm.processors.speaker_aware_processor import SpeakerAwareProcessor
from video_transcript_api.llm.core.key_info_extractor import KeyInfo
from video_transcript_api.llm.prompts.schemas.contradiction_scan import (
    CONTRADICTION_REASONS,
    CONTRADICTION_SCAN_SCHEMA,
)


def _config(**overrides):
    values = dict(
        api_key="k",
        base_url="http://test",
        calibrate_model="calibrate-model",
        summary_model="summary-model",
    )
    values.update(overrides)
    return LLMConfig(**values)


def _response(payload):
    response = MagicMock()
    response.structured_output = payload
    return response


def test_config_switch_defaults_on_and_accepts_nested_override():
    base = {
        "llm": {
            "api_key": "k",
            "base_url": "http://test",
            "calibrate_model": "calibrate-model",
            "summary_model": "summary-model",
        }
    }
    assert LLMConfig.from_dict(base).contradiction_scan_enabled is True
    base["llm"]["speaker_inference"] = {"contradiction_scan_enabled": False}
    assert LLMConfig.from_dict(base).contradiction_scan_enabled is False


def _dialogs(count=4):
    return [
        {
            "segment_id": f"seg_{i}",
            "speaker": "大卫" if i % 2 else "小丹尼",
            "speaker_id": f"Speaker{i % 2 + 1}",
            "text": f"text {i}",
        }
        for i in range(count)
    ]


def test_scanner_marks_valid_contradiction_and_passes_compact_input():
    client = MagicMock()
    client.call.return_value = _response(
        {
            "contradictions": [
                {
                    "segment_id": "seg_1",
                    "reason": "direct_address_conflict",
                    "evidence_segment_ids": ["seg_0"],
                }
            ]
        }
    )
    scanner = ContradictionScanner(client, model="scan-model")

    result = scanner.scan_contradictions(
        _dialogs(40),
        {"Speaker1": "小丹尼", "Speaker2": "大卫"},
        {"Speaker1": {"confidence": 0.8}},
        title="Title",
    )

    assert result == {
        "status": "completed",
        "segment_overrides": {
            "seg_1": {
                "status": "suspect",
                "assignment_source": "semantic_evidence",
                "reason": "direct_address_conflict",
                "evidence_segment_ids": ["seg_0"],
            }
        },
        "speaker_risk_flags": [],
    }
    call = client.call.call_args.kwargs
    assert call["model"] == "scan-model"
    assert "seg_0" in call["user_prompt"]
    assert "text 0" in call["user_prompt"]
    assert "speaker_mapping" in call["user_prompt"]


def test_scanner_prompt_caps_each_text_at_first_100_characters():
    client = MagicMock()
    client.call.return_value = _response({"contradictions": []})
    long_text = "a" * 101
    scanner = ContradictionScanner(client, model="scan-model")
    scanner.scan_contradictions(
        [{"segment_id": "seg_1", "speaker": "Alice", "speaker_id": "S1", "text": long_text}],
        {},
        {},
    )
    prompt = client.call.call_args.kwargs["user_prompt"]
    assert '"text": "' + ("a" * 100) + '"' in prompt
    assert '"text": "' + ("a" * 101) + '"' not in prompt


def test_scanner_skips_llm_when_prepared_segments_exceed_maximum(caplog):
    assert MAX_SCAN_SEGMENTS == 500
    client = MagicMock()
    scanner = ContradictionScanner(client, model="scan-model")

    with patch(
        "video_transcript_api.llm.core.contradiction_scanner.logger",
        logging.getLogger("contradiction_scanner_max_segments_test"),
    ), caplog.at_level(logging.WARNING):
        result = scanner.scan_contradictions(_dialogs(501), {}, {})

    client.call.assert_not_called()
    assert "Contradiction scan skipped because segment count 501" in caplog.text
    assert result == {
        "status": "skipped",
        "segment_overrides": {},
        "speaker_risk_flags": [],
    }


@pytest.mark.parametrize(
    ("extra_field", "extra_value"), [("name", "Alice"), ("reasoning", "free text")]
)
def test_scanner_discards_contradiction_with_hallucinated_extra_field(
    extra_field, extra_value
):
    client = MagicMock()
    entry = {
        "segment_id": "seg_1",
        "reason": "self_reference_conflict",
        "evidence_segment_ids": ["seg_0"],
        extra_field: extra_value,
    }
    client.call.return_value = _response({"contradictions": [entry]})

    result = ContradictionScanner(client).scan_contradictions(_dialogs(), {}, {})

    assert result["segment_overrides"] == {}


def test_scanner_logs_hallucinated_target_id_with_segment_count(caplog):
    client = MagicMock()
    client.call.return_value = _response(
        {
            "contradictions": [
                {
                    "segment_id": "seg_missing",
                    "reason": "self_reference_conflict",
                    "evidence_segment_ids": ["seg_0"],
                }
            ]
        }
    )
    scanner = ContradictionScanner(client)

    with patch(
        "video_transcript_api.llm.core.contradiction_scanner.logger",
        logging.getLogger("contradiction_scanner_test"),
    ), caplog.at_level(logging.WARNING):
        result = scanner.scan_contradictions(_dialogs(), {}, {})

    assert result["segment_overrides"] == {}
    assert "Contradiction scan dropped entry" in caplog.text
    assert "seg_missing" in caplog.text
    assert "target id hallucination" in caplog.text


def test_scanner_warns_when_dialogs_without_segment_id_are_skipped(caplog):
    client = MagicMock()
    client.call.return_value = _response({"contradictions": []})
    scanner = ContradictionScanner(client)
    dialogs = [{"speaker": "Alice", "text": "missing id"}] + _dialogs(2)

    with patch(
        "video_transcript_api.llm.core.contradiction_scanner.logger",
        logging.getLogger("contradiction_scanner_missing_id_test"),
    ), caplog.at_level(logging.WARNING):
        scanner.scan_contradictions(dialogs, {}, {})

    assert "Contradiction scan skipped 1 dialogs without segment_id" in caplog.text


def test_scanner_drops_entry_with_hallucinated_evidence_id():
    client = MagicMock()
    client.call.return_value = _response(
        {
            "contradictions": [
                {
                    "segment_id": "seg_1",
                    "reason": "self_reference_conflict",
                    "evidence_segment_ids": ["seg_0", "seg_missing"],
                }
            ]
        }
    )
    with patch(
        "video_transcript_api.llm.core.contradiction_scanner.logger"
    ) as mock_logger:
        result = ContradictionScanner(client).scan_contradictions(_dialogs(), {}, {})
    mock_logger.warning.assert_any_call(
        "Contradiction scan dropped entry for segment_id 'seg_1': "
        "evidence segment id hallucination"
    )
    assert result["status"] == "completed"
    assert result["segment_overrides"] == {}


def test_scanner_discards_all_overrides_when_more_than_twenty_percent_suspect():
    client = MagicMock()
    client.call.return_value = _response(
        {
            "contradictions": [
                {
                    "segment_id": f"seg_{i}",
                    "reason": "third_person_conflict",
                    "evidence_segment_ids": ["seg_0"],
                }
                for i in range(3)
            ]
        }
    )
    result = ContradictionScanner(client).scan_contradictions(_dialogs(10), {}, {})
    assert result["segment_overrides"] == {}
    assert result["speaker_risk_flags"] == ["semantic_scan_unreliable"]


@pytest.mark.parametrize(
    ("total", "suspect_count", "expected_overrides", "expected_flags"),
    [
        (5, 1, 1, ["semantic_contradiction_detected"]),
        (5, 2, 0, ["semantic_scan_unreliable"]),
    ],
)
def test_scanner_twenty_percent_boundary_is_not_unreliable_until_exceeded(
    total, suspect_count, expected_overrides, expected_flags
):
    client = MagicMock()
    client.call.return_value = _response(
        {
            "contradictions": [
                {
                    "segment_id": f"seg_{i}",
                    "reason": "third_person_conflict",
                    "evidence_segment_ids": ["seg_0"],
                }
                for i in range(suspect_count)
            ]
        }
    )
    result = ContradictionScanner(client).scan_contradictions(_dialogs(total), {}, {})
    assert len(result["segment_overrides"]) == expected_overrides
    assert result["speaker_risk_flags"] == expected_flags


@pytest.mark.parametrize("count", [3, 1])
def test_scanner_flag_boundaries(count):
    client = MagicMock()
    client.call.return_value = _response(
        {
            "contradictions": [
                {
                    "segment_id": f"seg_{i}",
                    "reason": "qa_adjacency_conflict",
                    "evidence_segment_ids": ["seg_0"],
                }
                for i in range(count)
            ]
        }
    )
    result = ContradictionScanner(client).scan_contradictions(_dialogs(100), {}, {})
    expected = ["semantic_contradiction_detected"] if count == 3 else []
    assert result["speaker_risk_flags"] == expected


def test_scanner_failure_is_reported_without_raising():
    client = MagicMock()
    client.call.side_effect = TimeoutError("boom")
    result = ContradictionScanner(client).scan_contradictions(_dialogs(), {}, {})
    assert result == {
        "status": "failed",
        "segment_overrides": {},
        "speaker_risk_flags": [],
    }


@pytest.mark.parametrize(
    ("total", "expected_flags"),
    [(34, []), (33, ["semantic_contradiction_detected"])],
)
def test_scanner_ratio_boundary_detects_one_of_thirty_three_only(total, expected_flags):
    client = MagicMock()
    client.call.return_value = _response(
        {
            "contradictions": [
                {
                    "segment_id": "seg_0",
                    "reason": "qa_adjacency_conflict",
                    "evidence_segment_ids": ["seg_0"],
                }
            ]
        }
    )
    result = ContradictionScanner(client).scan_contradictions(_dialogs(total), {}, {})
    assert result["speaker_risk_flags"] == expected_flags


def test_contradiction_schema_locks_reason_enum_and_unknown_fields():
    item_schema = CONTRADICTION_SCAN_SCHEMA["properties"]["contradictions"]["items"]
    assert tuple(item_schema["properties"]["reason"]["enum"]) == CONTRADICTION_REASONS
    assert ContradictionScanner.REASONS == frozenset(CONTRADICTION_REASONS)
    assert item_schema["additionalProperties"] is False
    assert CONTRADICTION_SCAN_SCHEMA["additionalProperties"] is False


def test_processor_sanitizer_derives_reasons_from_scanner(monkeypatch):
    monkeypatch.setattr(ContradictionScanner, "REASONS", frozenset({"dynamic_reason"}))
    override = {
        "status": "suspect",
        "assignment_source": "semantic_evidence",
        "reason": "dynamic_reason",
        "evidence_segment_ids": ["seg_0"],
    }

    sanitized = SpeakerAwareProcessor._sanitize_contradiction_overrides(
        {"seg_0": override}, {"seg_0"}
    )

    assert sanitized == {"seg_0": override}


@pytest.mark.parametrize(
    ("extra_field", "extra_value"), [("name", "Alice"), ("reasoning", "free text")]
)
def test_processor_sanitizer_discards_contradiction_with_hallucinated_extra_field(
    extra_field, extra_value, caplog
):
    override = {
        "status": "suspect",
        "assignment_source": "semantic_evidence",
        "reason": "self_reference_conflict",
        "evidence_segment_ids": ["seg_0"],
        extra_field: extra_value,
    }

    with patch(
        "video_transcript_api.llm.processors.speaker_aware_processor.logger",
        logging.getLogger("speaker_aware_processor_field_set_test"),
    ), caplog.at_level(logging.WARNING):
        sanitized = SpeakerAwareProcessor._sanitize_contradiction_overrides(
            {"seg_0": override}, {"seg_0"}
        )

    assert sanitized == {}
    assert "Contradiction override dropped for segment_id 'seg_0'" in caplog.text
    assert "field set mismatch" in caplog.text


def test_processor_sanitizer_discards_contradiction_with_hallucinated_evidence_id(
    caplog,
):
    override = {
        "status": "suspect",
        "assignment_source": "semantic_evidence",
        "reason": "self_reference_conflict",
        "evidence_segment_ids": ["seg_missing"],
    }

    with patch(
        "video_transcript_api.llm.processors.speaker_aware_processor.logger",
        logging.getLogger("speaker_aware_processor_evidence_test"),
    ), caplog.at_level(logging.WARNING):
        sanitized = SpeakerAwareProcessor._sanitize_contradiction_overrides(
            {"seg_0": override}, {"seg_0"}
        )

    assert sanitized == {}
    assert "Contradiction override dropped for segment_id 'seg_0'" in caplog.text
    assert "evidence segment id hallucination" in caplog.text


def test_processor_preserves_scanner_skipped_status():
    client = MagicMock()
    key_info = MagicMock()
    key_info.extract.return_value = KeyInfo([], [], [], [], [], [], [])
    inferencer = MagicMock()
    inferencer.infer.return_value = {
        "mapping": {"Speaker1": "Alice"},
        "meta": {},
        "source": "llm",
    }
    scanner = MagicMock()
    scanner.scan_contradictions.return_value = {
        "status": "skipped",
        "segment_overrides": {},
        "speaker_risk_flags": [],
    }
    processor = SpeakerAwareProcessor(
        _config(), client, key_info, inferencer, MagicMock(), contradiction_scanner=scanner
    )

    result = processor.process(
        [{"speaker": "Speaker1", "text": "hello", "start_time": 0, "end_time": 1}],
        title="slice",
        skip_calibration=True,
    )

    assert result["stats"]["contradiction_scan_status"] == "skipped"


def test_processor_runs_scan_after_segment_dedup_and_keeps_skip_calibration():
    client = MagicMock()
    key_info = MagicMock()
    key_info.extract.return_value = KeyInfo([], [], [], [], [], [], [])
    inferencer = MagicMock()
    inferencer.infer.return_value = {
        "mapping": {"Speaker1": "大卫"},
        "meta": {},
        "source": "llm",
    }
    scanner = MagicMock()
    scanner.scan_contradictions.return_value = {
        "status": "completed",
        "segment_overrides": {
            "seg_00000000_speaker1": {
                "status": "suspect",
                "assignment_source": "semantic_evidence",
                "reason": "direct_address_conflict",
                "evidence_segment_ids": ["seg_00000000_speaker1"],
            }
        },
        "speaker_risk_flags": ["semantic_contradiction_detected"],
    }
    processor = SpeakerAwareProcessor(
        _config(), client, key_info, inferencer, MagicMock(), contradiction_scanner=scanner
    )

    result = processor.process(
        [{"speaker": "Speaker1", "text": "刚才大卫", "start_time": 0, "end_time": 1}],
        title="slice",
        skip_calibration=True,
    )

    scanner.scan_contradictions.assert_called_once()
    assert result["stats"]["contradiction_scan_status"] == "completed"
    assert result["structured_data"]["segment_overrides"]
    assert "semantic_contradiction_detected" in result["structured_data"]["speaker_risk_flags"]


def test_processor_skips_scanner_without_speaker_and_disabled_gate():
    for has_speaker, infer_names, enabled, expected in [
        (False, True, True, "skipped"),
        (True, False, True, "disabled"),
        (True, True, False, "disabled"),
    ]:
        client = MagicMock()
        key_info = MagicMock()
        key_info.extract.return_value = KeyInfo([], [], [], [], [], [], [])
        inferencer = MagicMock()
        inferencer.infer.return_value = {"mapping": {}, "meta": {}, "source": "llm"}
        scanner = MagicMock()
        processor = SpeakerAwareProcessor(
            _config(contradiction_scan_enabled=enabled),
            client,
            key_info,
            inferencer,
            MagicMock(),
            contradiction_scanner=scanner,
        )
        result = processor.process(
            [{"speaker": "S1", "text": "x", "start_time": 0, "end_time": 1}]
            if has_speaker
            else [{"text": "x", "start_time": 0, "end_time": 1}],
            title="t",
            skip_calibration=True,
            has_speaker=has_speaker,
            infer_speaker_names=infer_names,
        )
        assert result["stats"]["contradiction_scan_status"] == expected
        scanner.scan_contradictions.assert_not_called()


def test_production_slice_s2_direct_address_override_and_flag():
    fixture_path = Path(__file__).parents[1] / "fixtures" / "speaker_observability" / "production_slice.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    client = MagicMock()
    key_info = MagicMock()
    key_info.extract.return_value = KeyInfo([], [], [], [], [], [], [])
    inferencer = MagicMock()
    inferencer.infer.return_value = {
        "mapping": fixture["mapping"],
        "meta": fixture["meta"],
        "source": fixture["source"],
    }
    scanner = MagicMock()

    def scan_result(**kwargs):
        s2_dialog = next(
            dialog for dialog in kwargs["dialogs"]
            if dialog.get("speaker_id") == "Speaker2" and "刚才大卫" in dialog.get("text", "")
        )
        return {
            "status": "completed",
            "segment_overrides": {
                s2_dialog["segment_id"]: {
                    "status": "suspect",
                    "assignment_source": "semantic_evidence",
                    "reason": "direct_address_conflict",
                    "evidence_segment_ids": [s2_dialog["segment_id"]],
                }
            },
            "speaker_risk_flags": ["semantic_contradiction_detected"],
        }

    scanner.scan_contradictions.side_effect = scan_result
    processor = SpeakerAwareProcessor(
        _config(), client, key_info, inferencer, MagicMock(), contradiction_scanner=scanner
    )
    result = processor.process(fixture["segments"], title="production slice", skip_calibration=True)
    assert result["stats"]["contradiction_scan_status"] == "completed"
    assert "semantic_contradiction_detected" in result["structured_data"]["speaker_risk_flags"]
    assert len(result["structured_data"]["segment_overrides"]) == 1
    override = next(iter(result["structured_data"]["segment_overrides"].values()))
    assert override["reason"] == "direct_address_conflict"
    assert "name" not in override
