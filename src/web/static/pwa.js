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
    // 消费完查询串即清掉地址栏：standalone 停留在带参 URL 时，
    // 刷新会重新预填覆盖当前输入（Codex R7-4）
    try {
      window.history.replaceState(null, '', window.location.pathname);
    } catch (e) { /* history API unavailable: cosmetic only */ }

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

  // beforeinstallprompt 顶层立即注册（Codex R7-3）：DOMContentLoaded 才注册
  // 存在错过提前触发事件的竞态，导致安装按钮永久隐藏；事件缓存在
  // deferredInstallPrompt，DOM 就绪后只做按钮绑定/显隐。
  var deferredInstallPrompt = null;
  if (typeof window !== 'undefined') {
    window.addEventListener('beforeinstallprompt', function (event) {
      event.preventDefault();
      deferredInstallPrompt = event;
      updateInstallButtonVisibility();
    });
    window.addEventListener('appinstalled', function () {
      deferredInstallPrompt = null;
      updateInstallButtonVisibility();
    });
  }

  function updateInstallButtonVisibility() {
    if (typeof document === 'undefined') {
      return; // DOM 未就绪（或 vitest）：事件已缓存，就绪后会再刷新
    }
    var btn = document.getElementById('pwa-install-btn');
    if (!btn) {
      return;
    }
    if (isStandalone() || dismissedRecently(DISMISS_KEY)) {
      btn.style.display = 'none';
      return;
    }
    if (deferredInstallPrompt) {
      btn.style.display = '';
      return;
    }
    // iOS: no beforeinstallprompt ever fires; offer the guided hint instead.
    if (isIOS() && !dismissedRecently(IOS_HINT_DISMISS_KEY)) {
      btn.textContent = '分享 → 添加到主屏幕';
      btn.setAttribute('aria-label', '查看安装引导：分享 → 添加到主屏幕');
      btn.style.display = '';
      return;
    }
    btn.style.display = 'none';
  }

  function initInstallButton() {
    var btn = document.getElementById('pwa-install-btn');
    if (!btn) {
      return;
    }

    btn.addEventListener('click', function () {
      if (deferredInstallPrompt) {
        var promptEvent = deferredInstallPrompt;
        btn.style.display = 'none';
        promptEvent.prompt();
        promptEvent.userChoice.then(function (choice) {
          if (choice.outcome === 'dismissed') {
            rememberDismiss(DISMISS_KEY);
          }
          if (deferredInstallPrompt === promptEvent) {
            deferredInstallPrompt = null;
          }
        });
      } else if (isIOS()) {
        showIosHint();
      }
    });

    // 事件可能已在 DOM 就绪前缓存，按当前状态刷新显隐
    updateInstallButtonVisibility();
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
  var SW_READY_TIMEOUT_MS = 5000;
  var NOTIFY_DENIED_HINT_KEY = 'vta_pwa_notify_denied_hint';
  var TRACKED_TASKS_KEY = 'vta_pwa_tracked_tasks';

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
   * Parse the persisted tracked-task list from localStorage JSON.
   * The list survives the standalone same-window jump to /view and page
   * refreshes (Codex R1-1), so it must tolerate junk writes.
   *
   * @param {?string} json Raw localStorage value.
   * @returns {Array<{task_id: string, view_token: string}>}
   */
  function parseTrackedTasks(json) {
    if (!json) {
      return [];
    }
    var list;
    try {
      list = JSON.parse(json);
    } catch (e) {
      return [];
    }
    if (!Array.isArray(list)) {
      return [];
    }
    return list
      .filter(function (t) {
        return t && typeof t.task_id === 'string' && t.task_id;
      })
      .map(function (t) {
        return {
          task_id: t.task_id,
          view_token: typeof t.view_token === 'string' ? t.view_token : '',
        };
      });
  }

  /**
   * Add a task to the list, deduping by task_id (latest wins).
   *
   * @param {Array} list Current list.
   * @param {{task_id: string, view_token: string}} task Task to track.
   * @returns {Array} New list.
   */
  function upsertTrackedTask(list, task) {
    var filtered = list.filter(function (t) {
      return t.task_id !== task.task_id;
    });
    filtered.push({ task_id: task.task_id, view_token: task.view_token || '' });
    return filtered;
  }

  /**
   * Remove a task by key (never by index: indices go stale across awaits,
   * Codex R1-3).
   *
   * @param {Array} list Current list.
   * @param {string} taskId Task id to remove.
   * @returns {Array} New list.
   */
  function removeTrackedTask(list, taskId) {
    return list.filter(function (t) {
      return t.task_id !== taskId;
    });
  }

  /**
   * Notification toggle (explicit user gesture, per design E5) plus the
   * task tracker listening for app.js 'vta:task-submitted'. The tracked
   * list is persisted to localStorage (Codex R1-1): the standalone
   * same-window jump to /view unloads this page, and an in-memory list
   * would silently drop every notification.
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
    // iOS 通知需 >=16.4 且必须从已安装 PWA（standalone）内请求；
    // 非 standalone 时按能力检测隐藏入口（设计 E5 / Codex R6-2）
    if (isIOS() && !isStandalone()) {
      return;
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
      // 权限请求必须由用户手势触发（本按钮点击即手势）；
      // 授权成功后恢复/启动已持久化任务的轮询（Codex R5-1）
      Notification.requestPermission()
        .then(function () {
          renderButton();
          resumePolling();
        })
        .catch(function (err) {
          // iOS 非 standalone 等场景 requestPermission 会直接 reject（Codex R6-2）
          console.warn('notification permission request failed:', err);
          if (typeof UIManager !== 'undefined') {
            UIManager.showStatus(
              'error',
              '通知授权失败',
              '请在已安装的应用内或浏览器设置中开启通知'
            );
          }
        });
    });

    // ---- 任务跟踪轮询（持久化到 localStorage，跨页面跳转/刷新存活） ----
    var tracked = []; // {task_id, view_token, failures}
    var timer = null;
    var pollInFlight = false;

    function persistTracked() {
      try {
        var list = tracked.map(function (t) {
          return { task_id: t.task_id, view_token: t.view_token };
        });
        if (list.length === 0) {
          window.localStorage.removeItem(TRACKED_TASKS_KEY);
        } else {
          window.localStorage.setItem(TRACKED_TASKS_KEY, JSON.stringify(list));
        }
      } catch (e) { /* storage unavailable: tracking stays in memory */ }
    }

    function addTracked(taskId, viewToken, startPolling) {
      var raw = upsertTrackedTask(
        tracked.map(function (t) {
          return { task_id: t.task_id, view_token: t.view_token };
        }),
        { task_id: taskId, view_token: viewToken }
      );
      // latest wins：新值的字段（含 view_token）生效，仅继承旧 failures 计数（Codex R5-3）
      tracked = raw.map(function (u) {
        var failures = 0;
        for (var i = 0; i < tracked.length; i++) {
          if (tracked[i].task_id === u.task_id) {
            failures = tracked[i].failures;
            break;
          }
        }
        return { task_id: u.task_id, view_token: u.view_token, failures: failures };
      });
      persistTracked();
      if (startPolling && !timer) {
        timer = setInterval(pollTracked, POLL_INTERVAL_MS);
      }
    }

    // 初始化时无论权限都把持久化列表恢复进内存 tracked（Codex R7-1）：
    // 否则未授予权限时提交新任务，会用只含新任务的列表覆盖 localStorage，
    // 旧任务静默丢失。仅「启动轮询」限制在 granted。
    function restoreTracked() {
      var persisted = [];
      try {
        persisted = parseTrackedTasks(window.localStorage.getItem(TRACKED_TASKS_KEY));
      } catch (e) { /* storage unavailable */ }
      persisted.forEach(function (u) {
        addTracked(u.task_id, u.view_token, false);
      });
    }

    // 权限已授予且有在跟踪任务时启动轮询；default/denied 一律不起轮询
    function resumePolling() {
      if (Notification.permission !== 'granted') {
        return;
      }
      if (typeof APIManager === 'undefined') {
        return; // E5 仅 index 页激活（复用 APIManager.getTaskStatus）
      }
      if (tracked.length > 0 && !timer) {
        timer = setInterval(pollTracked, POLL_INTERVAL_MS);
      }
    }

    document.addEventListener('vta:task-submitted', function (event) {
      if (typeof APIManager === 'undefined') {
        return; // E5 仅 index 页激活（复用 APIManager.getTaskStatus）
      }
      var detail = event.detail || {};
      if (!detail.task_id) {
        return;
      }
      // 无论权限状态都先 upsert 并持久化（Codex R5-1）：提交后才开通知是
      // 首次使用的常见路径；granted 立即起轮询，default 待用户点「开启通知」
      // 授权后经 resumePolling 启动，denied 只落盘不起轮询
      addTracked(
        detail.task_id,
        detail.view_token,
        Notification.permission === 'granted'
      );
    });

    // 恢复持久化列表（无论权限），granted 时随即启动轮询
    restoreTracked();
    resumePolling();

    async function pollTracked() {
      if (pollInFlight) {
        return; // 单飞：上一轮慢请求未结束不重入（Codex R1-3）
      }
      pollInFlight = true;
      try {
        var toRemove = [];
        for (var i = 0; i < tracked.length; i++) {
          var item = tracked[i];
          try {
            var body = await APIManager.getTaskStatus(item.task_id);
            var state = taskTerminalState(body);
            if (state === 'success') {
              try {
                // 投递成功才移出跟踪（Codex R3-1）；SW 回退投递失败时
                // 保留任务并计入 failures，靠连续 5 次失败自然收敛
                await notifySuccess(item);
                toRemove.push(item.task_id);
              } catch (notifyErr) {
                item.failures += 1;
                if (item.failures >= MAX_CONSECUTIVE_FAILURES) {
                  console.warn('E5 polling stopped after 5 failures:', item.task_id, notifyErr);
                  toRemove.push(item.task_id);
                }
              }
            } else if (state === 'failed') {
              toRemove.push(item.task_id); // 失败静默停止
            } else {
              item.failures = 0;
            }
          } catch (err) {
            item.failures += 1;
            if (item.failures >= MAX_CONSECUTIVE_FAILURES) {
              console.warn('E5 polling stopped after 5 failures:', item.task_id, err);
              toRemove.push(item.task_id);
            }
          }
        }
        // 按键值删除，不按 await 之前的下标 splice（Codex R1-3）
        toRemove.forEach(function (taskId) {
          tracked = removeTrackedTask(tracked, taskId);
        });
        if (toRemove.length) {
          persistTracked();
        }
      } finally {
        pollInFlight = false;
      }
      if (tracked.length === 0 && timer) {
        clearInterval(timer); // 列表空即停
        timer = null;
      }
    }

    /**
     * Deliver the completion notification.
     *
     * @returns {Promise<void>} Resolves once the notification is handed to
     *   the platform (page-level constructor, or SW showNotification on
     *   Android Chrome); rejects when delivery failed so the caller keeps
     *   the task tracked (Codex R3-1).
     */
    async function notifySuccess(item) {
      var title = '转录任务完成';
      var options = {
        body: '点击查看转录结果',
        icon: '/static/icons/icon-192.png',
      };
      var viewUrl = '/view/' + item.view_token;
      try {
        // 页面级 Notification：桌面可用，保留裁决的 onclick 跳 /view 行为
        var n = new Notification(title, options);
        n.onclick = function () {
          window.focus();
          window.location.href = viewUrl;
        };
      } catch (err) {
        // Android Chrome：页面上下文构造器直接抛 TypeError（Codex R1-2），
        // 回退经 Service Worker 发系统通知，点击由 sw.js notificationclick 处理；
        // await 投递结果，失败向上抛由轮询计数
        if ('serviceWorker' in window.navigator) {
          // SW 注册失败时 ready 永不 resolve：加超时让异常进入既有
          // failures 计数，避免 pollInFlight 卡死、轮询永久停摆（Codex R4-1）
          var reg = await Promise.race([
            window.navigator.serviceWorker.ready,
            new Promise(function (resolve, reject) {
              setTimeout(function () {
                reject(new Error('serviceWorker.ready timeout'));
              }, SW_READY_TIMEOUT_MS);
            }),
          ]);
          await reg.showNotification(
            title,
            Object.assign({}, options, { data: { url: viewUrl } })
          );
        } else {
          throw err;
        }
      }
    }
  }

  // Export pure functions for vitest (plain node, CJS via createRequire).
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
      taskTerminalState: taskTerminalState,
      POLL_INTERVAL_MS: POLL_INTERVAL_MS,
      MAX_CONSECUTIVE_FAILURES: MAX_CONSECUTIVE_FAILURES,
      SW_READY_TIMEOUT_MS: SW_READY_TIMEOUT_MS,
      TRACKED_TASKS_KEY: TRACKED_TASKS_KEY,
      parseTrackedTasks: parseTrackedTasks,
      upsertTrackedTask: upsertTrackedTask,
      removeTrackedTask: removeTrackedTask,
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
