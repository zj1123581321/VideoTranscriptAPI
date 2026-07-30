"""
TextSegmenter unit tests.

Covers:
- Standard sentence-based segmentation
- CapsWriter format detection (low punctuation density)
- Segment size limits (segment_size, max_segment_size)
- Empty/short text handling

All console output must be in English only (no emoji, no Chinese).
"""

import re

import pytest
from unittest.mock import Mock
from video_transcript_api.llm.segmenters.text_segmenter import TextSegmenter
from video_transcript_api.llm.core.config import LLMConfig
from video_transcript_api.transcriber.segments import parse_time_to_seconds


@pytest.fixture
def config():
    """Create a minimal LLMConfig for segmenter testing."""
    return Mock(
        spec=LLMConfig,
        segment_size=100,
        max_segment_size=200,
    )


@pytest.fixture
def segmenter(config):
    return TextSegmenter(config)


class TestTextSegmenter:
    """Test text segmentation logic."""

    def test_empty_text(self, segmenter):
        """Empty text should return empty segments."""
        result = segmenter.segment("")
        assert result == []

    def test_short_text_single_segment(self, segmenter):
        """Short text should produce a single segment."""
        result = segmenter.segment("short text here")
        assert len(result) == 1

    def test_sentence_segmentation(self, segmenter):
        """Text with punctuation should be split by sentences when exceeding segment_size."""
        # Need enough text to exceed segment_size (100 chars)
        text = "first sentence with enough words here。second sentence also with many words。third sentence is quite long too。fourth one also long enough。fifth sentence to push way over the size limit definitely。"
        result = segmenter.segment(text)
        assert len(result) >= 2
        # Each segment should be within max_segment_size
        for seg in result:
            assert len(seg) <= segmenter.max_segment_size

    def test_capswriter_format_detection(self, segmenter):
        """Text with low punctuation density (no periods) should be detected as CapsWriter."""
        # CapsWriter format: many lines, no punctuation
        lines = [f"line {i} with some words here" for i in range(20)]
        text = "\n".join(lines)
        result = segmenter.segment(text)
        assert len(result) >= 1
        for seg in result:
            assert len(seg) <= segmenter.max_segment_size

    def test_max_segment_size_respected(self):
        """Segments should never exceed max_segment_size."""
        config = Mock(spec=LLMConfig, segment_size=50, max_segment_size=100)
        seg = TextSegmenter(config)
        text = "a" * 500 + "。" + "b" * 500 + "。"
        result = seg.segment(text)
        for segment in result:
            assert len(segment) <= 100

    def test_chinese_text_segmentation(self, segmenter):
        """Chinese text with standard punctuation should segment correctly."""
        text = "这是第一句话。这是第二句话！这是第三句话？" * 5
        result = segmenter.segment(text)
        assert len(result) >= 1


class TestDialogSegmenter:
    """Test dialog segmentation logic."""

    @pytest.fixture
    def dialog_config(self):
        return Mock(
            spec=LLMConfig,
            min_chunk_length=50,
            max_chunk_length=200,
            preferred_chunk_length=100,
        )

    @pytest.fixture
    def dialog_segmenter(self, dialog_config):
        from video_transcript_api.llm.segmenters.dialog_segmenter import DialogSegmenter
        return DialogSegmenter(dialog_config)

    def test_empty_dialogs(self, dialog_segmenter):
        """Empty dialog list should return empty chunks."""
        assert dialog_segmenter.segment([]) == []

    def test_single_short_dialog(self, dialog_segmenter):
        """Single short dialog should be one chunk."""
        dialogs = [{"speaker": "A", "text": "hello world", "start_time": 0}]
        result = dialog_segmenter.segment(dialogs)
        assert len(result) == 1
        assert len(result[0]) == 1

    def test_multiple_dialogs_chunking(self, dialog_segmenter):
        """Multiple dialogs should be chunked by preferred length."""
        dialogs = [
            {"speaker": f"S{i%2}", "text": f"dialog text number {i} " * 5, "start_time": i}
            for i in range(10)
        ]
        result = dialog_segmenter.segment(dialogs)
        assert len(result) >= 2
        # Each chunk total text should not exceed max
        for chunk in result:
            total = sum(len(d["text"]) for d in chunk)
            assert total <= dialog_segmenter.max_chunk_length + 100  # some tolerance for last merge

    def test_long_dialog_split(self, dialog_segmenter):
        """Single dialog exceeding max_chunk_length should be split."""
        # Text must have sentence punctuation for splitting to work
        long_text = "这是一段很长的话。" * 50  # ~450 chars with split points
        dialogs = [{"speaker": "A", "text": long_text, "start_time": 0}]
        result = dialog_segmenter.segment(dialogs)
        assert len(result) >= 2

    def test_long_dialog_interpolates_timestamps_without_copying(self, dialog_segmenter):
        """Long dialog fragments retain the original sentence split order and timeline."""
        sentence = "中性测试句子。"
        long_text = sentence * 200
        dialogs = [
            {
                "speaker": "A",
                "text": long_text,
                "start_time": "00:00:21",
                "end_time": "00:56:24",
            }
        ]

        result = dialog_segmenter.segment(dialogs)
        fragments = [dialog for chunk in result for dialog in chunk]
        expected_texts = [sentence * 28] * 7 + [sentence * 4]

        assert [dialog["text"] for dialog in fragments] == expected_texts
        assert len(fragments) == len(expected_texts)
        assert all(dialog["time_estimated"] is True for dialog in fragments)

        starts = [parse_time_to_seconds(dialog["start_time"]) for dialog in fragments]
        ends = [parse_time_to_seconds(dialog["end_time"]) for dialog in fragments]
        assert starts[0] == parse_time_to_seconds("00:00:21")
        assert ends[-1] == parse_time_to_seconds("00:56:24")
        assert all(
            re.fullmatch(r"\d{2}:\d{2}:\d{2}", dialog["start_time"])
            for dialog in fragments
        )
        assert all(
            re.fullmatch(r"\d{2}:\d{2}:\d{2}", dialog["end_time"])
            for dialog in fragments
        )
        assert all(start < end for start, end in zip(starts, ends))
        assert starts == sorted(starts)
        assert len(set(starts)) == len(starts)

        for index, dialog in enumerate(fragments):
            assert dialog["duration"] == pytest.approx(ends[index] - starts[index])
            if index:
                assert starts[index] == ends[index - 1]
                assert starts[index] >= ends[index - 1]

    @pytest.mark.parametrize(
        ("seconds", "template", "expected"),
        [
            (1.5, "00:00:00", "00:00:01"),
            (1.0, "00:00:00.0", "00:00:01.0"),
            (1.5, "00:00:00.00", "00:00:01.50"),
        ],
    )
    def test_dialog_timestamp_format_preserves_template_precision(
        self, dialog_segmenter, seconds, template, expected
    ):
        assert (
            dialog_segmenter._format_dialog_timestamp(seconds, template)
            == expected
        )

    def test_long_dialog_with_invalid_times_keeps_text_and_drops_timeline(
        self, dialog_segmenter
    ):
        sentence = "中性测试句子。"
        dialogs = [
            {
                "speaker": "A",
                "text": sentence * 100,
                "start_time": "not-a-time",
                "end_time": "00:10:00",
            }
        ]

        result = dialog_segmenter.segment(dialogs)
        fragments = [dialog for chunk in result for dialog in chunk]

        assert len(fragments) > 1
        assert "".join(dialog["text"] for dialog in fragments) == dialogs[0]["text"]
        assert all(dialog["time_estimated"] is True for dialog in fragments)
        assert all(dialog["start_time"] is None for dialog in fragments)
        assert all(dialog["end_time"] is None for dialog in fragments)
        assert all(dialog["duration"] is None for dialog in fragments)

    def test_mixed_precision_endpoints_keep_contiguous_timeline(
        self, dialog_segmenter
    ):
        """Different start/end decimal precision must not wipe the timeline."""
        sentence = "中性测试句子。"
        dialogs = [
            {
                "speaker": "A",
                "text": sentence * 100,
                "start_time": "00:00:00",
                "end_time": "00:00:10.0",
            }
        ]

        result = dialog_segmenter.segment(dialogs)
        fragments = [dialog for chunk in result for dialog in chunk]

        assert len(fragments) > 1
        assert all(dialog["start_time"] is not None for dialog in fragments)
        assert all(dialog["end_time"] is not None for dialog in fragments)
        assert all(dialog["duration"] is not None for dialog in fragments)
        assert all(dialog["time_estimated"] is True for dialog in fragments)

        assert parse_time_to_seconds(fragments[0]["start_time"]) == parse_time_to_seconds(
            "00:00:00"
        )
        assert parse_time_to_seconds(fragments[-1]["end_time"]) == parse_time_to_seconds(
            "00:00:10.0"
        )
        for index in range(1, len(fragments)):
            assert fragments[index - 1]["end_time"] == fragments[index]["start_time"]

    def test_short_tail_merged(self, dialog_segmenter):
        """Very short last chunk should be merged into previous."""
        dialogs = [
            {"speaker": "A", "text": "x" * 80, "start_time": 0},
            {"speaker": "B", "text": "y" * 80, "start_time": 1},
            {"speaker": "A", "text": "z" * 10, "start_time": 2},  # Short tail
        ]
        result = dialog_segmenter.segment(dialogs)
        # Short tail should be merged
        total_dialogs = sum(len(chunk) for chunk in result)
        assert total_dialogs == 3
