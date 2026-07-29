/*
 * PWA glue for VideoTranscriptAPI (design: docs/designs/pwa.md T5).
 *
 * Loaded by both entry pages (index.html / history.html):
 *   - registers the service worker at /sw.js (root scope);
 *   - E1 install button state machine (beforeinstallprompt is Chromium-only):
 *     installable -> prompting -> installed (hidden); dismissed -> hidden
 *     with a 7-day cooldown recorded in localStorage;
 *   - iOS never fires beforeinstallprompt: the same spot shows a
 *     "Share -> Add to Home Screen" guided hint instead (dismissible).
 *
 * Everything degrades by capability detection: if serviceWorker or the
 * install prompt is unavailable, the button simply stays hidden.
 */
(function () {
  'use strict';

  var DISMISS_KEY = 'vta_pwa_install_dismissed';
  var IOS_HINT_DISMISS_KEY = 'vta_pwa_ios_hint_dismissed';
  var DISMISS_COOLDOWN_MS = 7 * 24 * 3600 * 1000;

  function isStandalone() {
    return (
      window.matchMedia('(display-mode: standalone)').matches ||
      window.navigator.standalone === true
    );
  }

  function isIOS() {
    var ua = window.navigator.userAgent;
    return (
      /iPad|iPhone|iPod/.test(ua) ||
      (window.navigator.platform === 'MacIntel' && window.navigator.maxTouchPoints > 1)
    );
  }

  function dismissedRecently(key) {
    try {
      var ts = Number(window.localStorage.getItem(key) || 0);
      return ts > 0 && Date.now() - ts < DISMISS_COOLDOWN_MS;
    } catch (e) {
      return false;
    }
  }

  function rememberDismiss(key) {
    try {
      window.localStorage.setItem(key, String(Date.now()));
    } catch (e) {
      /* storage unavailable: cooldown simply does not persist */
    }
  }

  function registerServiceWorker() {
    if (!('serviceWorker' in window.navigator)) {
      return;
    }
    window.navigator.serviceWorker.register('/sw.js').catch(function (err) {
      console.warn('SW registration failed:', err);
    });
  }

  /**
   * E4 share-target prefill (T7): /add_task_by_web?url=&title=&text=.
   * Fills the share textarea via .value (never innerHTML, S3-1) and triggers
   * the app's own input handling. Silent when no usable URL was shared.
   */
  function initSharePrefill() {
    if (!window.PWAShare) {
      return;
    }
    var textarea = document.getElementById('share-content');
    if (!textarea) {
      return; // only the index page carries the submit form
    }
    var sharedUrl = window.PWAShare.getSharedUrl(window.location.search);
    if (!sharedUrl) {
      return;
    }
    textarea.value = sharedUrl;
    textarea.dispatchEvent(new Event('input', { bubbles: true }));

    // app.js globals live in the shared script scope (not on window);
    // typeof guards keep this a no-op on pages without app.js.
    var ui = typeof UIManager !== 'undefined' ? UIManager : null;
    var hasToken = false;
    try {
      hasToken = !!(
        typeof StorageManager !== 'undefined' &&
        typeof APP_CONFIG !== 'undefined' &&
        StorageManager.get(APP_CONFIG.STORAGE_KEYS.BEARER_TOKEN)
      );
    } catch (e) {
      hasToken = false;
    }

    if (hasToken) {
      if (ui) {
        ui.showStatus('success', '已从分享填入链接');
      }
      return;
    }
    // 新设备无 token：预填会 401，聚焦高亮 token 输入框（复用 app.js 模式）
    var tokenInput = document.getElementById('bearer-token');
    if (tokenInput) {
      if (
        ui &&
        typeof isAdvancedSettingsExpanded !== 'undefined' &&
        !isAdvancedSettingsExpanded
      ) {
        ui.toggleAdvancedSettings();
      }
      setTimeout(function () {
        tokenInput.focus();
      }, 100);
      if (ui) {
        ui.showStatus('error', '请先配置访问令牌', '已从分享填入链接，配置令牌后即可提交');
      }
    }
  }

  function initInstallButton() {
    var btn = document.getElementById('pwa-install-btn');
    if (!btn || isStandalone()) {
      return;
    }

    var deferredPrompt = null;

    window.addEventListener('beforeinstallprompt', function (event) {
      event.preventDefault();
      deferredPrompt = event;
      if (!dismissedRecently(DISMISS_KEY)) {
        btn.style.display = '';
      }
    });

    window.addEventListener('appinstalled', function () {
      btn.style.display = 'none';
      deferredPrompt = null;
    });

    btn.addEventListener('click', function () {
      if (deferredPrompt) {
        btn.style.display = 'none';
        deferredPrompt.prompt();
        deferredPrompt.userChoice.then(function (choice) {
          if (choice.outcome === 'dismissed') {
            rememberDismiss(DISMISS_KEY);
          }
          deferredPrompt = null;
        });
      } else if (isIOS()) {
        showIosHint();
      }
    });

    // iOS: no beforeinstallprompt ever fires; offer the guided hint instead.
    if (isIOS() && !dismissedRecently(IOS_HINT_DISMISS_KEY)) {
      btn.style.display = '';
    }
  }

  function showIosHint() {
    if (document.getElementById('pwa-ios-hint')) {
      return;
    }
    var hint = document.createElement('div');
    hint.id = 'pwa-ios-hint';
    hint.setAttribute('role', 'dialog');
    hint.style.cssText =
      'position:fixed;left:16px;right:16px;bottom:16px;z-index:2000;' +
      'max-width:480px;margin:0 auto;padding:16px 20px;border-radius:12px;' +
      'background:var(--bg-primary,#fff);color:var(--text-primary,#222);' +
      'border:1px solid var(--border-primary,#ccc);box-shadow:0 8px 32px rgba(0,0,0,.25);' +
      'font-size:.9rem;line-height:1.7;';
    hint.innerHTML =
      '<strong>安装到主屏幕</strong><br>' +
      '1. 点击 Safari 底部的「分享」按钮<br>' +
      '2. 选择「添加到主屏幕」<br>' +
      '3. 点击「添加」即可像 App 一样使用';
    var close = document.createElement('button');
    close.type = 'button';
    close.textContent = '知道了';
    close.setAttribute('aria-label', '关闭安装引导');
    close.style.cssText =
      'display:block;margin:12px auto 0;min-height:44px;min-width:88px;' +
      'padding:8px 20px;border:none;border-radius:8px;cursor:pointer;' +
      'background:var(--accent-primary,#4f46e5);color:#fff;font-size:.85rem;';
    close.addEventListener('click', function () {
      rememberDismiss(IOS_HINT_DISMISS_KEY);
      hint.remove();
      var btn = document.getElementById('pwa-install-btn');
      if (btn) {
        btn.style.display = 'none';
      }
    });
    hint.appendChild(close);
    document.body.appendChild(hint);
  }

  // ---- E5 任务完成通知（T8，简化版：页面打开期间，仅 index 页激活） ----

  var POLL_INTERVAL_MS = 15000;
  var MAX_CONSECUTIVE_FAILURES = 5;
  var NOTIFY_DENIED_HINT_KEY = 'vta_pwa_notify_denied_hint';

  /**
   * Judge terminal state from the GET /api/task/{id} response BODY.
   * Failed tasks are HTTP 200 with body code=500, data.status='failed',
   * so the HTTP status is useless here (design E5, OV round-2 #1).
   *
   * @param {?object} body Parsed response body.
   * @returns {?string} 'success' | 'failed' when terminal, else null.
   */
  function taskTerminalState(body) {
    if (!body || typeof body !== 'object') {
      return null;
    }
    var data = body.data;
    if (!data || typeof data !== 'object') {
      return null;
    }
    if (data.status === 'success') {
      return 'success';
    }
    if (data.status === 'failed') {
      return 'failed';
    }
    return null;
  }

  /**
   * Notification toggle (explicit user gesture, per design E5) plus the
   * in-memory task tracker listening for app.js 'vta:task-submitted'.
   * In-memory by design: a page refresh loses tracking (accepted trade-off).
   */
  function initTaskNotifications() {
    if (!('Notification' in window)) {
      return; // capability detection: hide the entry entirely
    }
    var group = document.getElementById('pwa-notify-group');
    var btn = document.getElementById('pwa-notify-btn');
    if (!group || !btn) {
      return; // history.html has no toggle and no APIManager: stay inactive
    }
    group.style.display = '';

    function renderButton() {
      if (Notification.permission === 'granted') {
        btn.textContent = '通知已开启';
        btn.disabled = true;
      } else if (Notification.permission === 'denied') {
        // 永久隐藏入口 + 一次性提示去系统设置开
        group.style.display = 'none';
        var hinted = false;
        try {
          hinted = !!window.localStorage.getItem(NOTIFY_DENIED_HINT_KEY);
        } catch (e) { /* storage unavailable */ }
        if (!hinted) {
          try {
            window.localStorage.setItem(NOTIFY_DENIED_HINT_KEY, '1');
          } catch (e) { /* storage unavailable */ }
          if (typeof UIManager !== 'undefined') {
            UIManager.showStatus(
              'error',
              '通知权限已被拒绝',
              '请在浏览器/系统设置中允许本站通知后刷新页面'
            );
          }
        }
      } else {
        btn.textContent = '开启通知';
        btn.disabled = false;
      }
    }

    renderButton();
    btn.addEventListener('click', function () {
      // 权限请求必须由用户手势触发（本按钮点击即手势）
      Notification.requestPermission().then(renderButton);
    });

    // ---- 任务跟踪轮询（内存态，刷新即丢，预期行为） ----
    var tracked = [];
    var timer = null;

    document.addEventListener('vta:task-submitted', function (event) {
      if (Notification.permission !== 'granted') {
        return;
      }
      if (typeof APIManager === 'undefined') {
        return; // E5 仅 index 页激活（复用 APIManager.getTaskStatus）
      }
      var detail = event.detail || {};
      if (!detail.task_id) {
        return;
      }
      tracked.push({ taskId: detail.task_id, viewToken: detail.view_token, failures: 0 });
      if (!timer) {
        timer = setInterval(pollTracked, POLL_INTERVAL_MS);
      }
    });

    async function pollTracked() {
      for (var i = tracked.length - 1; i >= 0; i--) {
        var item = tracked[i];
        try {
          var body = await APIManager.getTaskStatus(item.taskId);
          var state = taskTerminalState(body);
          if (state === 'success') {
            notifySuccess(item);
            tracked.splice(i, 1);
          } else if (state === 'failed') {
            tracked.splice(i, 1); // 失败静默停止
          } else {
            item.failures = 0;
          }
        } catch (err) {
          item.failures += 1;
          if (item.failures >= MAX_CONSECUTIVE_FAILURES) {
            console.warn('E5 polling stopped after 5 failures:', item.taskId, err);
            tracked.splice(i, 1);
          }
        }
      }
      if (tracked.length === 0 && timer) {
        clearInterval(timer); // 列表空即停
        timer = null;
      }
    }

    function notifySuccess(item) {
      try {
        var n = new Notification('转录任务完成', {
          body: '点击查看转录结果',
          icon: '/static/icons/icon-192.png',
        });
        n.onclick = function () {
          window.focus();
          window.location.href = '/view/' + item.viewToken;
        };
      } catch (err) {
        console.warn('notification failed:', err);
      }
    }
  }

  // Export pure functions for vitest (plain node, CJS via createRequire).
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
      taskTerminalState: taskTerminalState,
      POLL_INTERVAL_MS: POLL_INTERVAL_MS,
      MAX_CONSECUTIVE_FAILURES: MAX_CONSECUTIVE_FAILURES,
    };
  }

  if (typeof document === 'undefined') {
    return; // imported under vitest (node): no DOM, nothing to wire
  }
  document.addEventListener('DOMContentLoaded', function () {
    registerServiceWorker();
    initInstallButton();
    initSharePrefill();
    initTaskNotifications();
  });
})();
