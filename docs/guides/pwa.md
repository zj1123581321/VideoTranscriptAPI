# PWA 使用与运维指南

对应设计：`docs/designs/pwa.md`（三轮评审定稿）。本文档覆盖手测清单、部署后验证与回滚 runbook。

## 功能入口

- 安装按钮：index / history 两页顶部导航区「📥 安装应用」。
  Chromium（桌面 Chrome/Edge + Android）走 `beforeinstallprompt`；用户拒绝后隐藏并冷却 7 天。
  iOS 不触发该事件，同位置改为「分享 → 添加到主屏幕」图文引导（可关闭，同样冷却 7 天）。
- 分享接收（仅 Android Chrome）：系统分享面板选择本 PWA，链接自动填入提交框。
  B站/抖音 App 常把链接混在 `text` 参数，前端自动提取第一个 URL。
  新设备未配置 token 时，提交框预填后会聚焦 token 输入框提示先配置。
- 任务完成通知：提交页「高级设置」内「开启通知」按钮显式授权；
  页面打开期间任务完成弹系统通知，点击直达结果页（失败任务静默停止）。
  权限被浏览器拒绝后入口永久隐藏。iOS 需 ≥16.4 且必须从已安装的 PWA 内授权。
- 已知边界：share_target 为 GET，完整 title/text 会拼进 URL（进访问日志、受 URL 长度限制），个人工具已接受。

## 手测清单（需真实浏览器逐项确认）

1. 桌面 Chrome/Edge：访问 `/add_task_by_web`，出现「📥 安装应用」按钮，点击安装成功。
2. 安装后以独立窗口（standalone，无地址栏）打开；manifest `display: standalone` 生效。
3. 长按/右键应用图标，出现 shortcuts「提交任务」「任务历史」直达。
4. standalone 窗口内提交任务：**不自动跳转**，停留在提交页（/view 是无 JS 静态页，
   跳过去 E5 轮询会死，Codex R2-1）；success 提示里的「点击查看任务进度」链接同窗口打开；
   任务完成后由通知 onclick 带去结果页。
5. 普通浏览器标签页内提交任务，行为回归：仍是新标签页打开结果页。
6. Android Chrome：从 B站 App 分享到本 PWA，链接自动填入；从抖音 App 分享同样验证。
7. 分享进入但本机无 token：聚焦 token 输入框并提示「请先配置访问令牌」。
8. E5：开启通知后提交任务，任务成功弹系统通知，点击通知聚焦并跳 `/view/{token}`；
   失败任务不弹通知、轮询静默停止。
9. iOS Safari：未安装时按钮位置显示「添加到主屏幕」引导；安装后从主屏幕打开为全屏。
10. iOS ≥16.4：从已安装 PWA 内点「开启通知」能弹系统授权。
11. 无痕窗口（无 token）：打开页面，DevTools → Application → Service Workers 显示 `/sw.js` 注册成功。
12. DevTools → Application → Cache Storage：只有当前版本的 `vta-static-v<N>`（旧版本已被 activate 清理），且只缓存入口页导航 / manifest / icons，
    `/api/*` 与 `/view/*` 不落盘。
13. 图标/manifest 变更后：确认已 bump `sw.js` 里 `CACHE_NAME` 版本号，旧 cache 在 activate 时被清理。

## 部署后验证

```bash
curl -sI https://<host>/sw.js
# 期望：200，Content-Type 含 javascript，Cache-Control: no-cache

curl -s https://<host>/static/manifest.webmanifest | head
# 期望：JSON，含 "display": "standalone"、"share_target"、"start_url": "/add_task_by_web"
```

再用无痕窗口打开站点，确认 SW 注册成功（见手测清单 11）。

## 回滚 runbook

普通回滚：按分支区间逐特性 revert（`git revert` 本分支相对 main 引入的提交，即
`origin/main..HEAD` 范围内的 PWA 相关 commit），SW 只缓存入口页导航与图标，驻留危害有限。

紧急下线（SW 已在用户浏览器驻留，需主动注销）：部署一个「自注销 SW」，
把 `src/web/static/sw.js` 整体替换为：

```js
// Self-uninstalling service worker: remove on next activate.
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((names) => Promise.all(names.filter((n) => n.startsWith('vta-static-')).map((n) => caches.delete(n))))
      .then(() => self.registration.unregister())
      .then(() => self.clients.matchAll())
      .then((clients) => clients.forEach((c) => c.navigate(c.url)))
  );
});
```

同时从 index.html / history.html 移除 `pwa.js` 的 `<script>` 引用（停止再次注册）。
用户下次访问时旧 SW 被替换、缓存清空、注册注销。

## 已知限制与 Backlog

- **多标签页相互干扰（Codex R2-2 / R5-2，接受不修）**：多个 index 标签页
  各自轮询同一任务，完成时可能重复通知；且各标签用本地完整 tracked 列表
  覆盖写 localStorage，关闭一个标签可能丢掉另一个标签持久化的任务。
  接受理由：自用工具实际单标签使用；修复需 Web Locks / storage 事件跨标签
  选主，属新机制，违反"不为 P2 新增机制"的纪律；最坏后果是重复一条通知
  或漏一条通知，无数据损失。若日后确实多标签高频使用，再评估选主方案。
- **过期任务可能弹延迟通知（Codex R3-2，接受不修）**：E5 跟踪列表持久化在
  localStorage，重开页面会恢复轮询；若任务在页面关闭期间已完成，下次打开
  index 页会补弹一条完成通知。接受理由：自用工具可接受，任务完成告知即使
  延迟仍有信息价值；如需收敛可在未来给跟踪项加 TTL，当前不加机制。
- **分享 URL 在 Response.url 元数据残留（Codex R5-4，接受不修）**：SW 的
  导航缓存键已按 pathname 规范化（不含查询串），但被缓存 Response 对象的
  `url` 元数据仍带完整分享 URL，严格说分享内容在 Cache Storage 有残留。
  接受理由：威胁模型是用户自己设备、自己 origin 的 Cache Storage，风险
  极低；彻底修复需重建响应流，为 P2 加复杂度不值得。代码行为不动。
