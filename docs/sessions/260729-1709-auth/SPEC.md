# 统一三页面浏览器 Bearer 鉴权规格

## 范围与风险

本 Session 将首页、历史页和转录结果页统一到浏览器 Bearer token 模块；后端
`verify_token`、权限/所有权检查和公有 `view_token` 阅读语义保持不变。不引入
cookie、OIDC、CSP/CORS、rate limit、TTL/rotation 或全量本地历史删除。

风险等级：`personal`。P1 红线是数据丢失、静默错误和崩溃；review 最多 8 轮，
连续 2 轮无新增 P1 后收敛。P2/P3 记录 backlog，可接受不修；修复优先做减法，
不得为 P2/P3 增加新状态、机制或配置。

## 不变式

1. canonical 键完整字面量为 `vta_bearer_token`。编码继续使用 Base64 + 反转 +
   固定后缀 `vta_encrypt_key_2024`；Base64 失败、后缀不匹配或 token 含控制字符时按
   absent 处理。合法 Base64 且后缀正确、但 payload 含非法 UTF-8 时，默认
   `TextDecoder` 以 U+FFFD 替换，结果通常会产生可见 401，可重新输入恢复；该边界按
   P2 接受不修。
2. 读取优先级固定为 canonical > localStorage `api_key` > localStorage
   `vta_api_key_persist` > sessionStorage `vta_api_key`；成功写 canonical 后删除别名。
3. `migrateAuthToken` 是显式/opt-in API；普通 legacy-only 初始化只按上述固定优先级
   读取，不承诺自动迁移。用户主动保存/更换或显式迁移成功时写 canonical，逐操作删除
   别名并写 `vta_auth_migration_v1` seal；仅读取旧键时它们可长期保留，重新保存 token
   会再次尝试 canonical 写入、清理别名和封存。clear 后不再读旧键。
   `storage` 事件清理其他标签页的 session alias，旧凭据不可复活。
4. localStorage 遇 SecurityError/QuotaExceededError 时降级内存且单次提示；拒绝
   控制字符；导出可检索的 `buildAuthHeaders`；compare-and-clear 仅在 token 快照
   相同时清除。
5. app.js 只适配 token 路径，StorageManager 的主题、Webhook、任务历史等偏好语义
   保持不变；auth-storage.js 必须先于 app.js 加载。
6. history change/clear 必须 abort 私有请求，并原子清空私有 list/stats/filter/
   selection/tooltip/current identity；不能删除主题或无关任务历史。
7. transcript 的 recalibrate/resummarize/generate notes 共用一次凭据对话和最多一
   次重放；缓存命中直接提交；403/404/409、POST TypeError/网络错误不得自动重放。
8. 轮询间隔 3 秒、最长 600 秒、连续错误阈值 10；单 in-flight、单 timer；状态按
   白名单处理，HTTP 200/body code=500 以 `data.status` 为准；unknown、非 JSON、缺
   task_id 显式失败，pagehide 必须 abort。
9. PWA service worker/资产版本必须缓存失效并加载新 auth 脚本；模板加载顺序有测试；
   复用已有 `escapeHTML`；共享脚本失败须显式禁用受保护操作。
10. 提供 clear/change 入口；dialog 支持 focus、Escape、Enter、ARIA；日志不得记录
    token 或完整敏感 URL。

## 已接受 P2 边界

以下两项按 R8 接受不修，不把它们表述为已修复，也不新增状态、回滚机制或持久键：

- canonical 写入成功后，别名删除或 migration marker 写入可能逐操作失败而残留；此时
  `writeAuthToken` 仍返回 `true`，当前 canonical 身份正确，只有 canonical 后续缺失时
  残留别名才可能复活。
- 当前 document 存储不可用时，memory 降级的 clear 返回 `false` 并保留 token，页面显示
  错误；关闭/重载，或存储恢复后重新输入 token，可恢复。

## 工程与交付约束

- 严格 TDD：先写失败测试并保留 RED 证据，再实现到 GREEN；每个增量不超过 3500
  行，绿后使用 `[codex]` 中文命令式提交、push，并更新 draft PR。
- 导出符号使用 2–4 词且含 auth 领域词；导出上方写单位、归属、时序等尖锐约束；
  错误/事件使用完整可 grep 字面量；token 不进入日志。
- 先运行本地 lint/test，再执行可用的 OCR 前置扫描；OCR `skipped` 时记录原因但不
  阻塞。随后进行独立 Codex review，按 personal 规则最多 8 轮，连续 2 轮无新增 P1
  收敛；无法溯源到规格的意见默认降为 P2/P3 并记 backlog。
- 本规格不授权修改后端鉴权、history/transcript/sw 以外的页面、部署或密钥配置。
