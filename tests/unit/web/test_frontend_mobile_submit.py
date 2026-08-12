"""Structural contracts for the mobile first-screen submission flow."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
STATIC_DIR = PROJECT_ROOT / "src" / "web" / "static"
INDEX_HTML = STATIC_DIR / "index.html"
APP_JS = STATIC_DIR / "js" / "app.js"
STYLES_CSS = STATIC_DIR / "css" / "styles.css"


def test_mobile_form_puts_options_auth_prompt_and_cta_in_first_screen_order():
    html = INDEX_HTML.read_text(encoding="utf-8")

    positions = [
        html.index('id="share-content"'),
        html.index('id="url-preview"'),
        html.index('id="transcription-options-toggle"'),
        html.index('id="auth-missing-prompt"'),
        html.index('id="submit-btn"'),
        html.index('id="advanced-settings"'),
    ]
    assert positions == sorted(positions)
    assert html.index('id="advanced-settings"') > html.index('id="submit-btn"')


def test_mobile_header_keeps_history_without_home_as_primary_nav():
    html = INDEX_HTML.read_text(encoding="utf-8")
    nav = html.split('<nav class="site-nav">', 1)[1].split("</nav>", 1)[0]

    assert 'href="/static/history.html"' in nav
    assert 'href="/"' not in nav
    assert 'id="theme-toggle"' not in nav
    assert 'id="pwa-install-btn"' in nav


def test_mobile_controls_expose_expansion_and_live_feedback_contracts():
    html = INDEX_HTML.read_text(encoding="utf-8")

    assert 'aria-live="polite"' in html
    assert 'aria-live="assertive"' in html
    assert 'aria-controls="transcription-options"' in html
    assert 'aria-controls="advanced-settings"' in html
    assert 'aria-expanded="false"' in html
    assert '尚未配置访问令牌' in html
    assert '去设置' in html


def test_empty_preview_is_hidden_and_invalid_input_has_inline_feedback():
    html = INDEX_HTML.read_text(encoding="utf-8")
    app = APP_JS.read_text(encoding="utf-8")

    assert 'id="url-preview" class="url-preview"' in html
    assert 'aria-live="polite" hidden' in html
    assert 'id="input-feedback"' in html
    assert 'class="input-feedback"' in html
    assert "previewContainer.hidden = urlResults.length === 0" in app
    assert "inputFeedback.textContent" in app
    assert "url-preview').innerHTML = '<div class=\"no-urls\">请输入包含视频链接的内容</div>'" not in app


def test_mobile_touch_targets_cover_navigation_and_submission_controls():
    css = STYLES_CSS.read_text(encoding="utf-8")

    assert ".site-nav-link" in css and "min-height: 44px" in css
    assert ".theme-toggle" in css and "width: 44px" in css
    assert ".submit-btn" in css and "min-height: 44px" in css
    assert ".transcription-options-toggle" in css and "min-height: 44px" in css
