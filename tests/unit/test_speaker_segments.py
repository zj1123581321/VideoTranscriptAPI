from unittest.mock import MagicMock

from video_transcript_api.llm.core.config import LLMConfig
from video_transcript_api.llm.core.key_info_extractor import KeyInfo
from video_transcript_api.llm.processors.speaker_aware_processor import SpeakerAwareProcessor


def _processor():
    config = LLMConfig(api_key="k", base_url="http://test", calibrate_model="test-model", summary_model="test-model")
    speaker = MagicMock()
    speaker.infer.return_value = {
        "mapping": {"Speaker1": "Alice", "Speaker2": "Bob"},
        "meta": {
            "Speaker1": {"name": "Alice", "confidence": 0.9, "applied": True},
            "Speaker2": {"name": "Bob", "confidence": 0.9, "applied": True},
        },
        "source": "llm",
    }
    key_info = MagicMock()
    key_info.extract.return_value = KeyInfo([], [], [], [], [], [], [])
    return SpeakerAwareProcessor(config, MagicMock(), key_info, speaker, MagicMock())


def test_segment_ids_sources_and_override_container_survive_process():
    result = _processor().process(
        [
            {"speaker": "Speaker1", "text": "first", "start_time": 1.25, "end_time": 2},
            {"speaker": "Speaker1", "text": "second", "start_time": 1.25, "end_time": 3},
            {"speaker": "Speaker2", "text": "other", "start_time": 4, "end_time": 5},
            {"speaker": "Speaker1", "text": "third", "start_time": 5, "end_time": 6},
        ], title="Test", skip_calibration=True
    )
    dialogs = result["structured_data"]["dialogs"]
    assert dialogs[0]["segment_id"] == "seg_00001250_speaker1"
    assert dialogs[0]["assignment_source"] == "global_mapping"
    assert dialogs[1]["segment_id"] == "seg_00004000_speaker2"
    assert dialogs[2]["segment_id"] == "seg_00005000_speaker1"
    assert result["structured_data"]["segment_overrides"] == {}
    assert result["structured_data"]["speaker_risk_flags"] == []


def test_correction_merge_preserves_observability_fields():
    original = {
        "start_time": "00:00:01", "end_time": "00:00:02", "duration": 1.0,
        "speaker": "Alice", "speaker_id": "Speaker1",
        "segment_id": "seg_00001000_speaker1", "assignment_source": "global_mapping",
        "text": "raw",
    }
    merged, _ = _processor()._apply_corrections_by_id([{"id": 0, "text": "corrected"}], [original])
    assert merged[0]["segment_id"] == original["segment_id"]
    assert merged[0]["assignment_source"] == "global_mapping"
    kept, _ = _processor()._apply_corrections_by_id([], [original])
    assert kept[0]["segment_id"] == original["segment_id"]
    assert kept[0]["assignment_source"] == "global_mapping"


def test_coerce_preserves_observability_fields_and_process_keeps_raw_speaker_id():
    processor = _processor()
    raw = [{
        "speaker": "Speaker1", "text": "hello", "start_time": 1,
        "segment_id": "seg_00001000_speaker1", "assignment_source": "global_mapping",
    }]
    coerced = processor._coerce_dialogs(raw)
    assert coerced[0]["segment_id"] == raw[0]["segment_id"]
    assert coerced[0]["assignment_source"] == "global_mapping"
    result = processor.process(raw, title="Test", skip_calibration=True)
    dialog = result["structured_data"]["dialogs"][0]
    assert dialog["speaker_id"] == "Speaker1"
    assert isinstance(result["structured_data"]["speaker_inference_meta"], dict)


def test_segment_id_conflicts_get_stable_suffixes():
    processor = _processor()
    dialogs = processor._normalize_and_merge_dialogs(
        [
            {"speaker": "Speaker1", "text": "one", "start_time": 2.0},
            {"speaker": "SPEAKER1", "text": "two", "start_time": 2.0},
        ],
        {},
    )
    assert [dialog["segment_id"] for dialog in dialogs] == [
        "seg_00002000_speaker1",
        "seg_00002000_speaker1-2",
    ]


def test_calibration_fragments_keep_unique_segment_ids():
    dialogs = [
        {"segment_id": "seg_00002000_speaker1", "text": "first"},
        {"segment_id": "seg_00002000_speaker1", "text": "second"},
    ]
    result = _processor()._deduplicate_segment_ids(dialogs)
    assert [dialog["segment_id"] for dialog in result] == [
        "seg_00002000_speaker1", "seg_00002000_speaker1-2"
    ]
