"""OG card footer label follows the C1 catalog.

All console output must be in English only (no emoji, no Chinese).
"""

from video_transcript_api.utils.rendering.og_card import _ai_label


def test_og_label_zh_cn(language_config):
    language_config("zh-CN")
    assert _ai_label() == "AI 总结"


def test_og_label_en(language_config):
    language_config("en")
    assert _ai_label() == "AI Summary"
