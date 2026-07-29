# 统一浏览器 Bearer 鉴权：实现与评审记录

> Session：`260729-1709-auth` · 风险等级：`personal`（自用工具）· 记录基于
> `origin/main...b133263` 的最终 diff。

## 结论

首页、任务历史页和转录结果页现在共享一个浏览器访问令牌模块。公开结果页和导出
链接仍是 `view_token` capability 的 GET 只读路径；提交任务、私有历史、重新校对、
重新总结和详细笔记等操作继续使用 Bearer 头。统一模块、历史页状态切换、受保护操作
控制器和 PWA 资产刷新契约均已落地，独立 review 在 R3/R4 连续两轮没有新增 P1，按
`personal` 规则曾收敛；后续 R6 发现两项 P1，已在本增量修复，当前不宣告最终收敛。
R7 又发现三项 P1，已在本增量修复，仍不宣告最终收敛。

## 实现清单

| 责任 | 实现位置 | 说明 |
| --- | --- | --- |
| canonical 存储、旧键迁移、跨标签同步、CAS 清除 | `src/web/static/js/auth-storage.js:9-369` | 统一导出 `readAuthToken`、`writeAuthToken`、`clearAuthToken`、`buildAuthHeaders` 和 `clearAuthTokenIfMatch`；存储失败降级到当前页内存。 |
| 首页适配 | `src/web/static/index.html:167-170`、`src/web/static/js/app.js:19-200,316-371` | `auth-storage.js` 先于 `app.js`；`StorageManager` 只转发访问令牌，主题、Webhook 和任务历史偏好仍走原有键。 |
| 历史页私有状态切换 | `src/web/static/history.html:603-733,919-999,1117-1148,1478-1499` | 查询/更换令牌前中止旧请求；清除原子重置列表、统计、过滤、选择、tooltip 和当前身份；请求代际与快照防迟到响应覆盖。 |
| 转录页受保护操作 | `src/web/static/js/transcript-protected-action.js:15-370`、`src/web/templates/transcript.html:393-639` | 三个 POST 共用一次提示、最多一次 401 重放和一个轮询控制器；对话框承担 ARIA、键盘和焦点返回。 |
| PWA 资产刷新 | `src/web/static/sw.js:23-33,52-71,111-154,184-238`、`src/web/templates/base.html:1072-1074` | `vta-static-v3` 版本化、鉴权脚本显式预缓存/network-first，API 和结果页不进入缓存。 |

## 关键不变式 → 代码与锁死测试

| # | 不变式（验收口径） | 代码落点 | 锁死测试 |
| --- | --- | --- | --- |
| 1 | canonical 键必须是完整字面量 `vta_bearer_token`；编码为 Base64+反转+固定后缀，后缀错误按 absent。 | `auth-storage.js:9-17,141-179` | `src/web/tests/auth-storage.test.js` 的 `auth token encoding` 两例；`tests/unit/web/test_frontend_auth.py::test_auth_module_keeps_canonical_storage_contract_literal`。 |
| 2 | 读取优先级为 canonical → `api_key` → `vta_api_key_persist` → `vta_api_key`；成功写 canonical 删除别名。 | `auth-storage.js:181-209,212-237` | `auth-storage.test.js` 的 `uses canonical...`、`falls back in ... priority`、`writes canonical storage...`。 |
| 3 | 主动选择/迁移优先复用有效 canonical；仅无 canonical 时才读取 legacy alias；迁移写 `vta_auth_migration_v1`，成功或 clear 后旧键不可复活；storage 事件清 session alias。 | `auth-storage.js:240-270,322-346` | `auth-storage.test.js` 的 `migrates... never resurrects`、`migrates canonical first...`、`clear seals aliases...`、`clears session aliases on storage events...`。 |
| 4 | `SecurityError`/`QuotaExceededError` 仅降级内存并单次告警；替换 token 前先清除旧 canonical，持久写失败不得让旧 token 刷新复活；旧 canonical 无法清除时保留原身份并返回失败；拒绝控制字符；Bearer 头可复用；401 仅 CAS 清相同快照。 | `auth-storage.js:25-107,109-111,220-297,308-327` | `auth-storage.test.js` 的控制字符、memory fallback、`does not resurrect persisted canonical...`、`keeps the previous identity when persisted canonical cannot be cleared`、`builds the unified Bearer header`、`compare-and-clears...`、`does not clear a newer persisted...`；`tests/unit/web/test_frontend_auth.py::test_api_requests_use_shared_header_builder`。 |
| 5 | 首页只适配 token 路径，监听共享模块 canonical/migration/legacy storage 事件并同步输入与 submit 状态；StorageManager 失败恢复真实身份；共享脚本先于页面脚本，缺失时 fail-closed。 | `app.js:40-97,133-200,1051-1065`；`index.html:167-170`；`base.html:1072-1074` | `auth-storage.test.js` homepage storage event、save failure/empty clear failure；`test_frontend_auth.py` 的首页加载顺序、storage contract、StorageManager 委托、缺失脚本安全错误、base 模板顺序。 |
| 6 | history clear/change abort 私有请求并原子清空私有状态，不删除主题/无关历史；canonical 或未封存 legacy alias 变化都必须触发同一 reset，迟到响应不得覆盖新身份。 | `history.html:654-733,1118-1148,1478-1499` | `src/web/tests/history-auth.test.js` 三例；`src/web/tests/history-auth-race.test.js` 六例及 `resets private state when an unsealed legacy alias changes...` 三场景（空查询、reset 后迟到 filter/history、new generation、分页/筛选乱序）；`test_frontend_auth.py::test_history_reset_and_401_contracts_are_explicit`。 |
| 7 | 已有令牌时 recalibrate/resummarize/generate notes 直接 POST；缺 token/首次 401 共用一次提示，最多重放一次；403/404/409、POST TypeError/网络错误不重放。 | `transcript-protected-action.js:15-19,117-142,271-315`；`transcript.html:499-559,608-636` | `transcript-protected-action.test.js` 的 cached token、single prompt、concurrent 401、late stale-token、one replay、403/404/409、`never replays an ambiguous POST TypeError`；`transcript-auth-integration.test.js` 的 cached-token/no prompt 与共享 dialog。 |
| 8 | 3 秒轮询、600 秒绝对超时、连续 10 次错误上限；单 in-flight/timer；白名单状态、body `code=500` 以 `data.status` 为准；非 JSON/缺字段显式失败；pagehide abort。 | `transcript-protected-action.js:20-23,159-269,317-331` | `transcript-protected-action.test.js` 的状态序列、HTTP 200/body 202、body 500 failed、unknown/missing、十次错误、401 poll、600000ms timeout（含未决 fetch abort）、pagehide。 |
| 9 | SW 版本升级刷新鉴权脚本；模板加载顺序可测；`escapeHTML` 复用；共享脚本失败显式禁用受保护操作。 | `sw.js:23-33,62-71,111-127`；`index.html:167-170`；`base.html:1072-1074`；`transcript.html:573-605`；`app.js:56-83` | `src/web/tests/sw.test.js` 的策略、版本、预缓存、network-first 回退；`test_frontend_auth.py::test_service_worker_versions_and_precaches_shared_auth_scripts`、模板顺序与 fail-closed；`app-escape.test.js` 的 preview/history escaping。 |
| 10 | 有 clear/change 入口；clear 删除/封存失败返回 false 且页面不显示成功、保持真实身份；对话框支持 focus、Escape、Enter、ARIA；日志/URL 不含 token 或完整敏感 URL。 | `history.html:479-490,726-738,837-864`；`transcript.html:393-413,499-545,624-641`；`auth-storage.js:273-337` | `transcript-auth-integration.test.js` 的 focus、Enter、Escape、focus restore、clear failure；`history-auth-race.test.js` 的 clear failure；`auth-storage.test.js` 的 canonical/alias/marker clear failure、CAS propagation、token 不进入告警验证。 |

## TDD 增量记录

实现按可独立变绿的故障域推进；每个增量先补失败契约，再实现并以 `[codex]` 提交。
提交链同时是 RED→GREEN 的可追溯锚点（未在本记录重复运行全量测试）。

| 增量 | 提交（时间顺序） | RED/GREEN 覆盖 |
| --- | --- | --- |
| A：统一存储与首页 | `209653e`、`4ffe786` | 编码/后缀、canonical/legacy 优先级、迁移/clear、memory fallback、CAS、首页加载顺序和 Bearer 头。 |
| B：历史页 | `252c1ca`、`d10f4ef`、`9324634`、`3f7f0eb`、`ae20a3e` | 私有状态原子 reset、请求代际、空查询、跨标签降级、分页/筛选乱序。 |
| C：结果页控制器与 PWA | `7dc5016`、`4c76e9f`、`54b6dc7`、`712b4f9`、`5389a59` | 三动作共享 controller、401/网络边界、轮询终态/超时/pagehide、详细笔记契约、SW 版本与脚本刷新。 |
| D：交互与竞态收口 | `b026f95`、`08d956a`、`3766faf`、`b9f558f`、`cadabeb`、`cfc86b8`、`b133263` | 取消焦点返回、主题 token、触控/可访问性/窄屏/术语、绝对超时 abort、持久 token compare-and-clear。 |

## OCR 前置扫描记录

OCR envelope（按本次 review 记录）：

```json
{"status":"reviewed","profile":"minimax","model":"MiniMax-M3","reason":"quota_sufficient"}
```

该扫描结果作为机械缺陷初筛；最终结论仍以独立 review 和测试契约为准。核实后的有效
P1 是 history 空输入查询误清 canonical，已由 `9324634` 修复并由
`src/web/tests/history-auth-race.test.js` 的 `does not clear the canonical token when an
empty input is queried` 锁死；其余 OCR finding 分别为 P2/P3 或误报，未直接转成修复。

## 独立 review 收敛记录

本次只审 `origin/main...HEAD`，规格为 `SPEC.md`，风险等级为 `personal`。

| 轮次 | 结果 | 处理 |
| --- | --- | --- |
| R1 | 发现 4 个 P1 | (1) `localStorage` 不可用时收到跨标签 `storage` 事件，内存仍持旧 token，后续 `401` 可能误删/回退（`3f7f0eb`）；(2) history 同 token 的分页/筛选旧响应覆盖新结果（`ae20a3e`）；(3) `pagehide` 发生在鉴权 prompt 期间，prompt 返回后仍可能 POST（`64cdb0f`）；(4) 单次 poll fetch 永不 resolve 可绕过 600 秒 deadline（`cfc86b8`）。 |
| R2 | 发现 1 个未闭合竞态 | 迟到 `401` 可能清掉另一标签页已持久化的新 token；`b133263` 增加 persisted canonical compare，`auth-storage.test.js` 的 `does not clear a newer persisted canonical token before its storage event arrives` 锁死。 |
| R3 | 无新增 P1 | 补充审查 token 术语、响应/状态白名单、脚本加载顺序、XSS 与 focus/disabled 行为；未扩大范围。 |
| R4 | 无新增 P1 | `/tmp/vta-codex-review-round4.txt` 记录“本轮无新增 P1”，覆盖存储/迁移/CAS、history reset/请求代际、POST/pagehide、600 秒轮询、XSS/敏感日志和 PWA 缓存；与 R3 连续两轮收敛。 |
| R6 | 发现 2 个 P1，已在本增量修复，尚未宣告最终收敛 | (1) 持久 canonical A 被替换为 B 时 `setItem` 失败，内存 B 刷新后会静默恢复 A；(2) 未封存迁移窗口内 legacy alias storage 事件未触发 history 原子 reset。回归测试覆盖 set 失败与旧 canonical 无法清除两个 storage 场景，以及 `api_key`/`vta_api_key_persist`/`vta_api_key` 三个事件键；修复提交：`30705e3`。 |
| R7 | 发现 3 个 P1，已在本增量修复，尚未宣告最终收敛 | (1) clear canonical/alias/marker 删除或封存失败曾假报成功；(2) 首页未同步共享 storage 事件；(3) 首页、history、transcript 未消费 clear/save false，可能显示新身份或成功文案。回归测试覆盖 canonical remove SecurityError、alias/marker failure、CAS propagation、首页事件/save/empty clear、history/transcript clear；修复提交：`5b880d3`。 |

R6 修复证据：旧实现 targeted RED 为 4 例（首个 storage 1 例、legacy 事件 3 例；旧
canonical 无法清除的边界由同一不变式锁死）；实现后
`auth-storage.test.js` 与 `history-auth-race.test.js` 共 41 例全绿，随后复跑 Web 与
Python Web 单测确认无回归。

R7 修复证据：旧实现 targeted RED 为 8 例；实现后 auth-storage、history-auth-race、
transcript-auth-integration targeted 共 53 例全绿，并通过 Python structural contract。

## CI 主审 finding 修复记录

- Finding：`migrateAuthToken()` 在 migration marker 尚未 sealed 且 canonical 与 legacy alias
  并存时按 legacy-first 选值，会用旧 alias 覆盖有效 canonical，违反统一存储的
  canonical-first 不变式。
- RED：新增 `auth-storage.test.js` 的 `migrates canonical first when canonical coexists...`
  回归（单个 alias 与全部 alias 两种场景），旧实现 2 例失败。
- Fix：`migrateAuthToken()` 无显式 token 时先解码 canonical，再回退 legacy；沿用现有
  `writeAuthToken()` 清理 alias 并 sealed marker。修复提交：`d238107`。

## P2/P3 backlog（接受不修）

以下项目不触及 personal 风险等级的 P1 红线，接受不修，不把已修复问题重复记入 backlog：

1. **清除后隐藏过滤选项仍留在 DOM**（P2）：history clear 已清空私有结果/统计等
   状态并隐藏过滤栏，但既有 filter option DOM 节点仍存在；这只是清除后视觉/DOM 清理
   的细节，不影响令牌或私有请求安全，留待独立 UX/DOM 清理任务。
2. **静态长任务反馈、缺少动态操作上下文**（P2）：结果页沿用“提交中/处理完成，
   正在刷新”等静态文案，controller 已明确状态和错误边界，但不引入新的后端进度协议
   或额外状态机；自用场景可接受，后续可在独立产品迭代增强。
3. **跨页视觉组件复用**（P2）：首页/历史页/结果页的令牌控件保持页面内样式和主题
   token，避免为本次安全修复引入共享 UI 构建链；视觉重复不改变行为，暂不扩 scope。
4. **SW 缓存写告警吞掉**（P2）：鉴权脚本读取仍 network-first，API/结果页不缓存；
   `cache.put(...).catch(() => {})` 的写失败只影响缓存命中，不影响当前网络响应或 token
   安全，故不为 P2 增加新的状态/配置，后续可补可观测性。
5. **首次 SecurityError 读取后的下一次 header 一致性**（P2）：当前实现沿用既有
   memory fallback 与单次告警，未为跨次可观测性增加状态或机制；自用场景可接受，后续
   可在独立存储可用性迭代补充。
6. **TextDecoder 非法 UTF-8 细分诊断**（P2）：非法 payload 按 absent 处理，不影响
   当前鉴权安全边界；不为本次 P1 清除流程新增解码状态，后续可补独立数据完整性测试。
