"""Structural contracts for homepage integration with shared browser auth."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
APP_JS = PROJECT_ROOT / "src" / "web" / "static" / "js" / "app.js"
AUTH_JS = PROJECT_ROOT / "src" / "web" / "static" / "js" / "auth-storage.js"
INDEX_HTML = PROJECT_ROOT / "src" / "web" / "static" / "index.html"
HISTORY_HTML = PROJECT_ROOT / "src" / "web" / "static" / "history.html"
BASE_HTML = PROJECT_ROOT / "src" / "web" / "templates" / "base.html"
TRANSCRIPT_HTML = PROJECT_ROOT / "src" / "web" / "templates" / "transcript.html"
PROTECTED_ACTION_JS = PROJECT_ROOT / "src" / "web" / "static" / "js" / "transcript-protected-action.js"
SW_JS = PROJECT_ROOT / "src" / "web" / "static" / "sw.js"


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


def test_history_uses_shared_auth_without_remember_dual_track():
    source = HISTORY_HTML.read_text(encoding="utf-8")
    assert source.index('/static/js/auth-storage.js') < source.index('<script>\n// ===================== 状态 =====================')
    assert "rememberKey" not in source
    assert "vta_api_key_persist" not in source
    assert "sessionStorage.setItem('vta_api_key'" not in source
    assert "authStorage.buildAuthHeaders()" in source


def test_history_reset_and_401_contracts_are_explicit():
    source = HISTORY_HTML.read_text(encoding="utf-8")
    assert "function resetPrivateHistoryState" in source
    assert "abortPrivateHistoryRequests" in source
    assert "const requestSnapshot = authStorage.snapshotAuthToken()" in source
    assert "authStorage.clearAuthTokenIfMatch(requestSnapshot)" in source
    assert "安全错误：统一鉴权模块加载失败，已禁用历史私有操作" in source
    assert "esc(item.title)" in source
    assert "esc(item.view_token)" in source


def test_base_loads_versioned_auth_before_page_extra_scripts():
    source = BASE_HTML.read_text(encoding="utf-8")
    auth_position = source.index('/static/js/auth-storage.js?v=')
    extra_position = source.index('{% block extra_js %}')
    assert auth_position < extra_position


def test_transcript_loads_versioned_controller_after_shared_auth():
    source = TRANSCRIPT_HTML.read_text(encoding="utf-8")
    assert '/static/js/transcript-protected-action.js?v=' in source
    assert source.index('/static/js/transcript-protected-action.js?v=') > source.index('{% block extra_js %}')
    assert 'var transcriptViewToken = {{ view_token|tojson }};' in source


def test_transcript_has_one_accessible_credential_dialog_and_three_actions():
    source = TRANSCRIPT_HTML.read_text(encoding="utf-8")
    assert source.count('<dialog ') == 1
    assert 'id="protectedActionAuthDialog"' in source
    assert 'aria-labelledby="protectedActionAuthTitle"' in source
    assert 'aria-describedby="protectedActionAuthDescription"' in source
    assert '<label for="protectedActionTokenInput">' in source
    assert 'id="protectedActionAuthChange"' in source
    assert 'id="protectedActionAuthClear"' in source
    for action in ("recalibrate", "resummarize", "generate_notes"):
        assert f"'{action}'" in source
    assert 'createProtectedActionController' in source


def test_transcript_removes_private_credential_and_handwritten_polling_paths():
    source = TRANSCRIPT_HTML.read_text(encoding="utf-8")
    for legacy in (
        "recalibrateApiKey",
        "resummarizeApiKey",
        "generateNotesApiKey",
        "localStorage.setItem('api_key'",
        "function pollTask",
        "fetch('/api/recalibrate'",
        "fetch('/api/resummarize'",
        "fetch('/api/generate_notes'",
        ".innerHTML",
    ):
        assert legacy not in source


def test_transcript_missing_shared_scripts_fails_closed_and_uses_safe_status_updates():
    source = TRANSCRIPT_HTML.read_text(encoding="utf-8")
    assert "安全错误：统一鉴权模块加载失败，已禁用受保护操作" in source
    assert "button.disabled = true" in source
    assert "textContent" in source
    assert "createElement('span')" in source
    assert "location.reload" in source


def test_service_worker_versions_and_precaches_shared_auth_scripts():
    source = SW_JS.read_text(encoding="utf-8")
    assert "const CACHE_NAME = 'vta-static-v3';" in source
    assert "'/static/js/auth-storage.js'" in source
    assert "'/static/js/transcript-protected-action.js'" in source
    assert "self.addEventListener('install'" in source
    assert "PRECACHE_ASSETS.map" in source
    assert "cache.add(asset)" in source
    assert "self.addEventListener('activate'" in source
