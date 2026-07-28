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
