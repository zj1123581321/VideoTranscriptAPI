import json
from pathlib import Path

from video_transcript_api.llm.core.speaker_inferencer import build_speaker_risk_flags


def test_risk_flags_boundaries_and_dropped_cluster_ratio():
    result = {"meta": {
        "Speaker1": {"confidence": 0.9, "applied": True, "sampled": True},
        "Speaker4": {"confidence": 0.4, "applied": False, "sampled": True},
    }}
    dialogs = [{"speaker": "Speaker1"}] * 19 + [{"speaker": "Speaker4"}]
    assert build_speaker_risk_flags(result, dialogs) == ["low_confidence_cluster_dropped"]
    result["meta"]["Speaker1"]["confidence"] = 0.7
    result["meta"]["Speaker4"]["confidence"] = 0.7
    assert build_speaker_risk_flags(result, dialogs) == []
    result["meta"]["Speaker1"]["confidence"] = 0.69
    assert build_speaker_risk_flags(result, dialogs) == ["low_average_mapping_confidence"]


def test_dropped_cluster_ratio_exactly_five_percent_triggers():
    result = {"meta": {"Speaker4": {"confidence": 0.4, "applied": False, "sampled": True}}}
    dialogs = [{"speaker": "Speaker1"}] * 19 + [{"speaker": "Speaker4"}]
    assert build_speaker_risk_flags(result, dialogs) == ["low_confidence_cluster_dropped"]


def test_dropped_cluster_ratio_below_five_percent_does_not_trigger():
    result = {"meta": {"Speaker4": {"confidence": 0.4, "applied": False, "sampled": True}}}
    dialogs = [{"speaker": "Speaker1"}] * 20 + [{"speaker": "Speaker4"}]
    assert build_speaker_risk_flags(result, dialogs) == []


def test_average_mapping_confidence_exactly_point_seven_does_not_trigger():
    result = {"meta": {
        "Speaker1": {"confidence": 0.7, "applied": True, "sampled": True},
        "Speaker2": {"confidence": 0.7, "applied": True, "sampled": True},
    }}
    assert build_speaker_risk_flags(result, [{"speaker": "Speaker1"}]) == []


def test_average_mapping_confidence_below_point_seven_triggers():
    result = {"meta": {
        "Speaker1": {"confidence": 0.7, "applied": True, "sampled": True},
        "Speaker2": {"confidence": 0.69, "applied": True, "sampled": True},
    }}
    assert build_speaker_risk_flags(result, [{"speaker": "Speaker1"}]) == [
        "low_average_mapping_confidence"
    ]


def test_legacy_meta_without_applied_ignores_mapping_name_equivalence():
    result = {
        "mapping": {"Speaker1": "Alice", "Speaker2": "Bob"},
        "meta": {
            "Speaker1": {"name": "Alice", "confidence": 0.59, "sampled": True},
            "Speaker2": {"name": "Bob", "confidence": 0.8, "sampled": True},
        },
    }
    assert build_speaker_risk_flags(
        result, [{"speaker": "Speaker1"}]
    ) == ["low_confidence_cluster_dropped"]


def test_legacy_meta_without_applied_uses_sampled_and_confidence_gate():
    result = {
        "mapping": {"Speaker4": "Alice"},
        "meta": {
            "Speaker4": {
                "name": "Different name",
                "confidence": 0.4,
                "sampled": True,
            }
        },
    }
    dialogs = [{"speaker": "Speaker1"}] * 19 + [{"speaker": "Speaker4"}]
    assert build_speaker_risk_flags(result, dialogs) == [
        "low_confidence_cluster_dropped"
    ]


def test_production_fixture_keeps_low_confidence_and_anchor_phrases():
    fixture = Path(__file__).parents[1] / "fixtures" / "speaker_observability" / "production_slice.json"
    data = json.loads(fixture.read_text(encoding="utf-8"))
    assert data["source"] == "llm"
    assert data["low_confidence"] == ["Speaker4"]
    assert data["meta"]["Speaker4"]["applied"] is False
    assert data["meta"]["Speaker4"]["confidence"] == 0.4
    segments = data["segments"]
    assert any(segment["speaker"] == "Speaker4" for segment in segments)
    assert any("刚才大卫" in segment["text"] for segment in segments)
    assert any("自然" in segment["text"] for segment in segments if segment["start_time"] >= 4057)
    flags = build_speaker_risk_flags({"meta": data["meta"]}, segments)
    assert "low_confidence_cluster_dropped" in flags
