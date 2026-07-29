# 统一浏览器 Bearer 鉴权：实现与评审记录

> Session：`260729-1709-auth` · 风险等级：`personal`（自用工具）· 记录基于
> `origin/main...d5672d2` 的当前 diff。

## 结论

首页、任务历史页和转录结果页现在共享一个浏览器访问令牌模块。公开结果页和导出
链接仍是 `view_token` capability 的 GET 只读路径；提交任务、私有历史、重新校对、
重新总结和详细笔记等操作继续使用 Bearer 头。统一模块、历史页状态切换、受保护操作
控制器和 PWA 资产刷新契约均已落地，独立 review 在 R3/R4 连续两轮没有新增 P1，按
`personal` 规则曾收敛；后续 R6 发现两项 P1，已在本增量修复，当前不宣告最终收敛。
R7 又发现三项 P1，已在本增量修复，仍不宣告最终收敛。R8 的最新 CI primary audit
报告两项 major；经用户分诊均降为 personal 风险下的 P2、接受不修，未新增代码修复。
按原始 8 轮上限，R7 后当前阶段仅 R8 这一轮按分诊结果 clean，不声称两轮无 P1 或
最终收敛；后续按用户要求继续 CI Agent Review 循环。

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
| R7 | 发现 3 个 P1，已在本增量修复，尚未宣告最终收敛 | (1) clear canonical/alias/marker 删除或封存失败曾假报成功；(2) 首页未同步共享 storage 事件；(3) 首页、history、transcript 未消费 clear/save false，可能显示新身份或成功文案。回归测试覆盖 canonical remove SecurityError、alias/marker failure、CAS propagation、首页事件/save/empty clear、history/transcript clear；修复提交：`1126152`。 |
| R8（用户分诊） | 无新增 P1（两项 CI primary audit major 均降为 P2，接受不修） | A：canonical 写成功后 alias 删除或 migration marker 写入失败，后续仅在 canonical 缺失/损坏时旧 alias 才可能复活；B：存储不可用进入当前页内存降级后 clear 失败恢复 `previousMemoryToken`。两项均只在逐键存储异常、浏览器策略或故障下触发；不新增状态、回滚协议或持久键。R7 后当前阶段仅 R8 这一轮按分诊结果 clean，后续继续 CI Agent Review 循环。 |

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

## 最新 CI primary audit findings（R8 用户分诊）

最新 CI primary audit 针对当前 HEAD `d5672d2` 报告两项 major。用户已将两项均按
`personal` 风险分诊为 P2，接受不修；本记录不声称新增代码修复，也不引入新的状态、
回滚协议或持久键。

1. **canonical 成功写入后的 alias/marker 部分失败**（P2，接受不修）：触发条件是
   canonical `setItem` 已成功，但某个 legacy alias 的 `removeItem` 或迁移 marker 的
   `setItem` 因逐键存储异常、浏览器策略或暂时故障失败。此时 `writeAuthToken()` 仍返回
   `true`；只要 canonical 后续仍可读，新 token 继续生效，只有 canonical 日后缺失或
   损坏时，未清掉的旧 alias 才可能被读取而复活旧身份。存储辅助层会把单键异常转为
   布尔结果并按既有策略告警；canonical 写入或 clear 的失败路径由页面检查布尔返回值并
   显式报错，不是静默地宣称已完成。该 finding 特指 canonical 成功后的 alias/marker
   部分成功边界，当前不为其增加汇总状态。恢复存储后重新输入/更换 token，或清理站点
   存储后再输入，可清除残留 alias 并恢复一致身份。
2. **内存降级 clear 失败恢复旧 token**（P2，接受不修）：触发条件是
   `localStorage`/`sessionStorage` 因逐键 `SecurityError`、浏览器策略或故障不可用，
   当前 document 已进入内存降级，随后用户执行 clear，而删除或 marker 写入仍失败。
   `clearAuthToken()`/CAS 会返回 `false`，页面沿用现有失败文案；内存 token 仅存在于
   当前 document 生命周期，关闭或重载标签页即可清掉。存储恢复后重新输入/更换 token，
   或清理站点存储后重新输入，可恢复正常持久化与清除能力；不为此增加新的回滚协议。

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
6. **TextDecoder 非法 UTF-8 细分诊断**（P2）：会成为含替换字符的无效 bearer，通常得到
   可见 401，不会静默切换到另一有效身份；因此在 personal 下接受不修，不为本次 P1 清除
   流程新增解码机制，后续可补独立数据完整性测试。
7. **canonical 写成功后的 alias/marker 部分失败**（P2）：逐键存储异常、浏览器策略或
   暂时故障才会触发；canonical 仍可读时不会改变当前身份，只有 canonical 日后缺失或
   损坏才可能让残留旧 alias 复活。页面已对 canonical write/clear 的失败检查布尔结果并
   报错，故障可由浏览器告警和页面错误观察；不新增部分成功汇总状态。恢复存储后重新
   输入/更换 token，或清理站点存储后再输入，可恢复一致状态。用户分诊接受不修。
8. **内存降级 clear 失败恢复 `previousMemoryToken`**（P2）：localStorage/sessionStorage
   受逐键 SecurityError、浏览器策略或故障影响而不可用时才触发；clear/CAS 返回 `false`
   并由页面显示失败，不静默宣称清除成功。内存 token 只属于当前 document，关闭或重载
   标签页即可清掉；存储恢复后重新输入/更换 token，或清理站点存储后再输入，可恢复。
   用户分诊接受不修，不增加新的回滚协议或持久键。

## Stack2 local gate review

本节是 Stack 2 的本地 gate review 记录，不计为 R9；原独立 review 的 8 轮上限保持不变。

### P1 修复：转录页受保护操作并发

发现：转录页每个按钮原先只禁用自身；多个受保护操作可并发启动。任一操作成功后
`scheduleSafeReload()` 会把所有 disabled 按钮误标为“处理完成”，500ms 刷新又会因
`pagehide` 中止其余轮询，造成 `task_id`、失败提示和实际结果静默丢失。

修复提交：`34908c4`（`[codex] 阻止转录页受保护操作并发`）。三个受保护按钮统一带
`data-protected-action` 标记，handler 在自身同步 disabled 前检查
`[data-protected-action]:disabled`；已有 in-flight 操作时直接忽略后续点击，沿用既有
`finally` 恢复路径，不新增业务状态、协议或持久键。

回归证据：旧实现 targeted RED 为 9 个测试中 1 个失败（首个动作 pending 时第二次
调用 controller）；修复后 `transcript-auth-integration.test.js` 9/9 GREEN。映射测试已
改为三个动作逐次 await/settle 后验证 action/view token，避免把并发点击当成契约。
随后 `npm run test:web` 为 10 files / 138 tests 全绿，`uv run pytest tests/unit/web
tests/unit/test_detailed_notes_view.py` 为 60 passed，`git diff --check` 通过。

后续 Stack2 local gate review 发现：`34908c4` 只覆盖首动作仍 pending 时的第二次点击，
未覆盖 success 回调到 500ms reload timer 执行之间的窗口。`aeaf6c3`（`[codex] 闭合受保护
操作刷新前并发窗口`）在首个 handler 同步禁用全部受保护按钮，仅将 active area 标为
`aria-busy`/running；reload 只把该 active area 标为完成，失败 catch 后恢复全部按钮。
回归新增 pending、success→reload 前点击和失败全量恢复三条断言：旧实现 targeted RED
为 10 tests 中 2 failures，修复后 targeted GREEN 10/10；随后 `npm run test:web` 为
10 files / 139 tests 全绿，Python Web 单测仍为 60 passed。该 finding 与修复属于同一
Stack2 local gate 循环，不计为 R9。

### 其他 finding 分诊

- **POST body `code=202`（P3/误报，接受不修）**：真实三个后端成功响应均返回
  `code=202` 与 `data.task_id`；controller 已显式校验两者，不改实现。
- **poll 401 后 prompt 取消或 token save 失败（P2，接受不修）**：最多多进行一次
  3 秒轮询，随后以可见错误终止；不会造成数据丢失、静默错误或崩溃。按分诊结论不为
  该边界增加新机制、状态或持久键。
- **polling budget 从 prompt/POST 前开始计时（P2，接受不修）**：真实触发需要凭据
  对话或 POST 消耗接近/超过 600 秒；任务创建后可能立即显示明确的 timeout，但不是
  静默成功、数据丢失或崩溃。后端任务独立继续，稍后刷新页面可看到最终缓存结果；也可
  重新发起，但提示注意避免重复。不新增计时状态或阶段机制。
- **initial prompt 后 POST/poll 401 再次 prompt（P2，接受不修）**：触发需要首次无
  token 且用户输入的 token 随后被服务端返回 401；第二个弹窗可见且可取消，用户可以
  输入正确 token 或取消，不会产生静默错误、数据丢失或崩溃。不新增 `hasPrompted`
  状态。
- **3 秒 timer deadline 最多 overshoot 3 秒（P3，接受不修）**：调度抖动可能让 deadline
  最多晚 3 秒触发，但任务最终状态或显式 timeout 不会丢失；不为此新增剩余预算调度。

以上三项均属于同一 Stack2 local gate 循环的后续 finding，不计为 R9，也不声称有代码
修复。
