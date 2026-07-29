"""Structural contracts for homepage integration with shared browser auth."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
APP_JS = PROJECT_ROOT / "src" / "web" / "static" / "js" / "app.js"
AUTH_JS = PROJECT_ROOT / "src" / "web" / "static" / "js" / "auth-storage.js"
INDEX_HTML = PROJECT_ROOT / "src" / "web" / "static" / "index.html"


def test_homepage_loads_auth_storage_before_app():
    html = INDEX_HTML.read_text(encoding="utf-8")
    auth_position = html.index('/static/js/auth-storage.js')
    app_position = html.index('/static/js/app.js')
    assert auth_position < app_position


def test_storage_manager_delegates_every_token_operation():
    source = APP_JS.read_text(encoding="utf-8")
    assert "authStorage.readAuthToken()" in source
    assert "authStorage.writeAuthToken(value, { remember: true })" in source
    assert "authStorage.clearAuthToken()" in source
    assert "simpleEncrypt" not in source
    assert "simpleDecrypt" not in source


def test_api_requests_use_shared_header_builder():
    source = APP_JS.read_text(encoding="utf-8")
    assert source.count("authStorage.buildAuthHeaders()") >= 2
    assert "'Authorization': `Bearer ${token}`" not in source


def test_missing_auth_script_fails_closed_with_visible_safety_error():
    source = APP_JS.read_text(encoding="utf-8")
    assert "VideoTranscriptAuthStorage" in source
    assert "安全错误：统一鉴权模块加载失败，已禁用受保护操作" in source
    assert "禁用受保护操作" in source


def test_url_preview_keeps_escape_html_at_all_external_interpolation_points():
    source = APP_JS.read_text(encoding="utf-8")
    assert 'data-url="${escapeHTML(result.url)}"' in source
    assert 'value="${escapeHTML(result.url)}"' in source
    assert 'class="url-display">${escapeHTML(result.display)}</span>' in source


def test_auth_module_keeps_canonical_storage_contract_literal():
    source = AUTH_JS.read_text(encoding="utf-8")
    assert "vta_bearer_token" in source
    assert "vta_encrypt_key_2024" in source
    assert "vta_auth_migration_v1" in source
