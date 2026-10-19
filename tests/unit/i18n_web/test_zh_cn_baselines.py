"""zh-CN render output matches Base-generated goldens.

All console output must be in English only (no emoji, no Chinese).
"""

from html.parser import HTMLParser
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from video_transcript_api.api.routes import views as views_mod
from video_transcript_api.utils.rendering.home_page import render_home_html
from video_transcript_api.utils.rendering.i18n_jinja import install_i18n
from video_transcript_api.utils.rendering.og_card import _ai_label

from tests.tools.generate_zh_cn_baselines import RESULT_CONTEXT

BASELINES = Path(__file__).resolve().parent / "fixtures" / "baselines"
TEMPLATES_DIR = Path(__file__).resolve().parents[3] / "src" / "web" / "templates"


class _VisibleText(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs) -> None:
        if tag in ("script", "style"):
            self._skip += 1

    def handle_endtag(self, tag) -> None:
        if tag in ("script", "style") and self._skip:
            self._skip -= 1

    def handle_data(self, data) -> None:
        if self._skip:
            return
        text = " ".join(data.split())
        if text:
            self.parts.append(text)


def visible_text(html: str) -> str:
    parser = _VisibleText()
    parser.feed(html)
    return "\n".join(parser.parts)


def test_home_html_matches_base_golden(language_config):
    language_config("zh-CN")
    golden = (BASELINES / "home.html").read_text(encoding="utf-8")
    assert render_home_html() == golden


def test_jinja_pages_match_base_goldens(language_config):
    language_config("zh-CN")
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(["html", "xml"]),
    )
    install_i18n(env)
    env.globals["asset_v"] = "baseline"
    pages = {
        "result.txt": "transcript.html",
        "processing.txt": "processing.html",
        "error.txt": "error.html",
        "cleaned.txt": "cleaned.html",
    }
    for filename, template_name in pages.items():
        current = env.get_template(template_name).render(**RESULT_CONTEXT)
        golden = (BASELINES / filename).read_text(encoding="utf-8")
        assert visible_text(current) + "\n" == golden, filename


def test_static_titles_match_base_golden():
    import json

    snapshots = json.loads((BASELINES / "static_titles.json").read_text(encoding="utf-8"))
    index = (TEMPLATES_DIR.parent / "static" / "index.html").read_text(encoding="utf-8")
    history = (TEMPLATES_DIR.parent / "static" / "history.html").read_text(encoding="utf-8")
    assert snapshots["submit"]["title"] in index
    assert snapshots["history"]["title"] in history


def test_export_header_and_og_label_zh_cn(language_config):
    language_config("zh-CN")
    header = views_mod._build_text_metadata_header(
        {"title": "Demo", "platform": "youtube"}, "calibrated"
    )
    assert "Type: 校对文本" in header
    assert _ai_label() == "AI 总结"
