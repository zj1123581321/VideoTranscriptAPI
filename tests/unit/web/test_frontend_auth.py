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


def test_homepage_syncs_shared_auth_storage_events_and_save_failures():
    source = APP_JS.read_text(encoding="utf-8")
    assert "window.addEventListener('storage', handleHomepageAuthStorageEvent)" in source
    assert "AUTH_STORAGE_KEYS" in source
    assert "仍使用当前访问令牌" in source
    assert "e.target.value = StorageManager.get(APP_CONFIG.STORAGE_KEYS.BEARER_TOKEN) || ''" in source


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


def test_history_and_transcript_clear_failures_are_visible():
    history = HISTORY_HTML.read_text(encoding="utf-8")
    transcript = TRANSCRIPT_HTML.read_text(encoding="utf-8")
    assert "if (!storage.clearAuthToken())" in history
    assert "鉴权清除失败" in history
    assert "if (!authStorage.clearAuthToken())" in transcript
    assert "访问令牌清除失败，当前令牌仍保留。" in transcript


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


def test_transcript_auth_controls_have_explicit_theme_owned_layout():
    source = TRANSCRIPT_HTML.read_text(encoding="utf-8")
    assert ".protected-action-auth-tools {" in source
    assert "margin: 24px 0;" in source
    assert "padding: 12px 16px;" in source
    assert "border: 1px solid var(--border-primary);" in source
    assert "background: var(--bg-secondary);" in source
    assert "var(--border-color" not in source
    assert "var(--accent-color" not in source


def test_transcript_auth_controls_have_touch_focus_and_disabled_contracts():
    source = TRANSCRIPT_HTML.read_text(encoding="utf-8")
    assert ".recalibrate-btn {" in source and "min-height: 44px;" in source
    assert ".recalibrate-dialog input {" in source and "min-height: 44px;" in source
    assert ".dialog-btn {" in source and "min-height: 44px;" in source
    assert ".recalibrate-btn:focus-visible" in source
    assert ".dialog-btn:focus-visible" in source
    assert ".recalibrate-dialog input:focus-visible" in source
    assert ".recalibrate-btn:disabled" in source
    assert ".dialog-btn:disabled" in source


def test_history_auth_controls_have_touch_focus_disabled_and_contrast_contracts():
    source = HISTORY_HTML.read_text(encoding="utf-8")
    assert ".auth-bar input {" in source and "min-height: 44px;" in source
    assert ".auth-bar .btn {" in source and "min-height: 44px;" in source
    assert ".auth-bar input:focus-visible" in source
    assert ".auth-bar button:focus-visible" in source
    assert ".auth-bar input:disabled" in source
    assert ".auth-bar button:disabled" in source
    assert "border: 1px solid var(--success-border);" in source
    assert "border: 1px solid var(--error-border);" in source
    assert "font-weight: 600;" in source


def test_auth_controls_have_narrow_screen_wrapping_contracts():
    transcript = TRANSCRIPT_HTML.read_text(encoding="utf-8")
    history = HISTORY_HTML.read_text(encoding="utf-8")
    assert "@media (max-width: 480px)" in transcript
    assert ".protected-action-auth-tools {" in transcript
    assert "flex-direction: column;" in transcript
    assert ".dialog-actions {" in transcript
    assert "flex-wrap: wrap;" in transcript
    assert ".auth-status {" in history
    assert "white-space: normal;" in history
    assert "overflow-wrap: anywhere;" in history
    assert ".auth-bar {" in history
    assert "min-width: 0;" in history


def test_auth_user_facing_terms_use_access_token_across_pages():
    index = INDEX_HTML.read_text(encoding="utf-8")
    history = HISTORY_HTML.read_text(encoding="utf-8")
    transcript = TRANSCRIPT_HTML.read_text(encoding="utf-8")
    app = APP_JS.read_text(encoding="utf-8")

    assert "API访问令牌 (Bearer Token)" not in index
    assert "Bearer Token" not in history.split("<script", 1)[0]
    assert "API Key" not in transcript
    assert "Bearer token" not in transcript
    assert "请先设置API访问令牌" not in app
    assert "请先设置 API 令牌" not in app
    assert "API 访问令牌（Bearer Token）" not in app
    for source in (index, history, transcript, app):
        assert "访问令牌" in source


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
    assert "const CACHE_NAME = 'vta-static-v4';" in source
    assert "'/static/js/auth-storage.js'" in source
    assert "'/static/js/transcript-protected-action.js'" in source
    assert "self.addEventListener('install'" in source
    assert "PRECACHE_ASSETS.map" in source
    assert "cache.add(asset)" in source
    assert "self.addEventListener('activate'" in source
