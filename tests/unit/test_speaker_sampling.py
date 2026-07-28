from unittest.mock import MagicMock

from video_transcript_api.llm.core.speaker_inferencer import SpeakerInferencer


def test_sampling_uses_head_middle_tail_and_sees_late_pollution():
    inferencer = SpeakerInferencer(MagicMock(), samples_per_speaker=3)
    dialogs = [{"speaker": "Speaker4", "text": f"head-{i}", "start_time": i} for i in range(9)]
    samples = inferencer._extract_sample_dialogs(dialogs, ["Speaker4"])
    assert samples["Speaker4"]["own_samples"] == ["head-0", "head-4", "head-8"]


def test_sampling_fewer_than_k_keeps_original_time_order():
    inferencer = SpeakerInferencer(MagicMock(), samples_per_speaker=3)
    dialogs = [
        {"speaker": "Speaker4", "text": "first", "start_time": 10},
        {"speaker": "Speaker4", "text": "second", "start_time": 11},
    ]
    samples = inferencer._extract_sample_dialogs(dialogs, ["Speaker4"])
    assert samples["Speaker4"]["own_samples"] == ["first", "second"]


def test_sampling_default_budget_keeps_head_middle_tail_samples():
    inferencer = SpeakerInferencer(MagicMock())
    dialogs = [
        {"speaker": "Speaker4", "text": "HEAD-" + "h" * 500, "start_time": 0},
        {"speaker": "Speaker4", "text": "early", "start_time": 1},
        {"speaker": "Speaker4", "text": "MIDDLE-" + "m" * 500, "start_time": 2},
        {"speaker": "Speaker4", "text": "late", "start_time": 3},
        {"speaker": "Speaker4", "text": "TAIL_MARKER", "start_time": 4},
    ]

    own_samples = inferencer._extract_sample_dialogs(dialogs, ["Speaker4"])["Speaker4"][
        "own_samples"
    ]

    assert len(own_samples) == 3
    assert all(own_samples)
    assert any("TAIL_MARKER" in sample for sample in own_samples)
    assert sum(map(len, own_samples)) <= 400


def test_sampling_per_sample_budget_preserves_tail_when_budget_is_tight():
    inferencer = SpeakerInferencer(
        MagicMock(), samples_per_speaker=3, max_chars_per_speaker=200
    )
    dialogs = [
        {"speaker": "Speaker4", "text": "HEAD-" + "h" * 500, "start_time": 0},
        {"speaker": "Speaker4", "text": "early", "start_time": 1},
        {"speaker": "Speaker4", "text": "MIDDLE-" + "m" * 500, "start_time": 2},
        {"speaker": "Speaker4", "text": "late", "start_time": 3},
        {"speaker": "Speaker4", "text": "TAIL_MARKER", "start_time": 4},
    ]

    own_samples = inferencer._extract_sample_dialogs(dialogs, ["Speaker4"])["Speaker4"][
        "own_samples"
    ]

    assert len(own_samples) == 3
    assert all(own_samples)
    assert any("TAIL_MARKER" in sample for sample in own_samples)
    assert sum(map(len, own_samples)) <= 200
