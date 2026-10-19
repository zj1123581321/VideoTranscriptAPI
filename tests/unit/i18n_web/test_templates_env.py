"""Production Jinja env exposes C1 catalog helpers.

All console output must be in English only (no emoji, no Chinese).
"""

from video_transcript_api.api.routes import views as views_mod
from video_transcript_api.i18n import get_language, t, web_catalog_script
from video_transcript_api.utils.rendering.i18n_jinja import html_lang, og_locale


def test_production_templates_env_exposes_i18n_globals():
    env = views_mod.templates.env
    assert env.globals["t"] is t
    assert env.globals["html_lang"] is html_lang
    assert env.globals["og_locale"] is og_locale


def test_web_catalog_script_exports_web_keys_only(language_config):
    language_config("en")
    payload = web_catalog_script(get_language())
    assert 'window.__VTA_LANG__ = "en"' in payload
    assert "window.I18N =" in payload
    assert "web.home.cta_submit" in payload
    assert "render.speaker.pending" not in payload
