"""Landing page and export metadata follow the C1 catalog.

All console output must be in English only (no emoji, no Chinese).
"""

from video_transcript_api.api.routes import views as views_mod


def test_home_html_en_switches_copy_and_lang(language_config):
    language_config("en")
    html = views_mod._render_home_html()
    assert 'lang="en"' in html
    assert "Multi-platform video transcription with AI proofreading" in html
    assert "Submit a task" in html
    assert "Task history" in html
    assert "多平台视频转录与 AI 智能校对服务" not in html


def test_export_metadata_header_zh_cn(language_config):
    language_config("zh-CN")
    header = views_mod._build_text_metadata_header(
        {"title": "Demo", "platform": "youtube"}, "calibrated"
    )
    assert "Type: 校对文本" in header
    assert "Title: Demo" in header


def test_export_metadata_header_en(language_config):
    language_config("en")
    header = views_mod._build_text_metadata_header(
        {"title": "Demo", "platform": "youtube"}, "calibrated"
    )
    assert "Type: Proofread transcript" in header
    assert "Type: 校对文本" not in header


def test_download_filename_follows_language(language_config):
    language_config("zh-CN")
    zh_name = views_mod.generate_download_filename("Demo", "bilibili", "summary")
    assert "总结文本" in zh_name
    assert "哔哩哔哩" in zh_name

    language_config("en")
    en_name = views_mod.generate_download_filename("Demo", "bilibili", "summary")
    assert "Summary" in en_name
    assert "Bilibili" in en_name
    assert "总结文本" not in en_name
