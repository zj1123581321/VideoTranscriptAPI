# C5 API errors progress

### 里程碑 1：JSON API 错误响应本地化
- 当前阶段：implementing
- 本段结论：新增稳定 `error_code` 和本地化字符串 `detail` 的响应处理；覆盖任务、审计、上传、用户配置与令牌校验错误，并保持默认中文文案逐字一致。新增测试锁定静态/动态错误文本、英文无 CJK、真实鉴权与空 URL 响应，以及 FastAPI 422 原形状。
- 关键决策与已否决方案：由 `ApiError` 按错误文案映射稳定代码，集中异常处理器序列化；不改 HTML 路由、前端或 422 请求体。
- 下一步唯一动作：完成 task_status 失败原因写入路径盘点；因 `llm_ops.py` 超出当前 Scope-Globs，已提交 seq 1 scope-request，获准后仅补该文件的失败原因本地化。

### 里程碑 2：全量测试与错误码映射补齐
- 当前阶段：implementing
- 本段结论：`make test` 首轮发现 `generate_notes` 的跨用户拒绝文案未映射；补齐 `notes_ownership_denied` 后，窄测和全量测试均通过。FastAPI 默认 422 校验错误仍保持只有 `detail` 的原形状。
- 关键决策与已否决方案：未将未映射错误静默降级为通用文案；按 fail-fast 映射具体文案与稳定错误码，并让全量测试验证遗漏。
- 下一步唯一动作：处理 seq 1 scope-request 对 `llm_ops.py` 的审批结果，覆盖剩余 task_status 写入路径或在报告中明确未授权边界。

### 里程碑 3：验证收敛与权限边界
- 当前阶段：blocked
- 本段结论：窄验证、全量 `make test`、Python 编译检查和 card scope 检查均通过；英文错误文案无 CJK，两个 locale 的 key 集合相同且按字典序排列。seq 1 的 `llm_ops.py` scope-request 在 120 秒等待后仍无审批结果，该文件两个 `task_status.error_message` 写入点因此未改，C5 的失败原因本地化目标尚未闭合。
- 关键决策与已否决方案：不越权修改未获批准的 `llm_ops.py`；保留 `notify_error` 与日志原文、只本地化已授权文件中的 task_status 写入，不迁移历史失败数据。
- 下一步唯一动作：由主脑处理 seq 1 scope-request；获批后本执行器只需本地化 `llm_ops.py` 两个失败写入点并重跑验收，未批准则按当前 failed/blocked 报告收尾。

### 里程碑 4：英文 API 行为验收
- 当前阶段：blocked
- 本段结论：补齐真实路由层 `language=en` 的无效令牌、缺失任务和空 URL 请求断言，响应均断言实际 JSON 序列化 payload 中的字符串 `detail` 与稳定 `error_code`。
- 关键决策与已否决方案：以 TestClient 读取响应体验证 HTTP 序列化边界，不用对异常对象的同进程断言替代 API 契约。
- 下一步唯一动作：对这次仅测试与进度文件的增量再跑 Accept-Check 与 scope 检查，然后提交并推送；`llm_ops.py` 未获 scope 仍按 blocked 上报。

### 里程碑 5：锁定生产应用注册
- 当前阶段：blocked
- 本段结论：新增 `create_app` 注册异常处理器的断言，并与独立的 TestClient 序列化测试配套；窄测通过，移除测试时启动未绑定 Runtime 的错误探针。
- 关键决策与已否决方案：不为验证处理器而启动完整服务生命周期；独立测试验证 JSON payload，生产 app 测试锁定异常处理器的实际注册。
- 下一步唯一动作：对最终测试文件状态运行全量 Accept-Check 与 scope 检查后提交、推送；未授权的 `llm_ops.py` 保持不变。

### 里程碑 6：授权范围内的交付收敛
- 当前阶段：blocked
- 本段结论：`make test` 与窄验证通过，scope 检查通过，分支已推送且工作区干净；JSON API 错误码、本地化及已授权的任务失败写入路径均已提交。由于 seq 1 scope-request 等待超时，`llm_ops.py` 两处 task_status 失败写入未能纳入，故不能宣告 C5 全目标完成。
- 关键决策与已否决方案：按卡面授权只提交 scope 内产物；没有绕过 scope 闸，也没有把未授权的 task_status 写入伪称为已本地化。
- 下一步唯一动作：主脑处理 dispatch `dlg-20261019-171404-e584c4` 的 seq 1 scope-request；获批后补改 `llm_ops.py` 并重新验收，否则由主脑按当前 blocked 交付验收。

### 里程碑 7：修订 A——调用点显式错误码
- 当前阶段：implementing
- 本段结论：删除按中文 detail 反查错误码的实现；已授权 JSON 路由与鉴权调用点改为显式 `ApiError(status_code, error_code, **values)`，动态错误部分通过 locale 占位符格式化。新增 AST 判据扫描 routes（排除 views）及 transcription 服务。
- 关键决策与已否决方案：保留原生 422 校验异常；不对未知文案作错误码推断，不引入默认/回退翻译。
- 下一步唯一动作：提交并推送本段 A；提交后执行一次 AST 断言红验，随后进入 C 任务失败原因保真。

### 里程碑 9：修订 C——task_status 失败原因保真
- 当前阶段：implementing
- 本段结论：删除 `localize_task_error`；`transcription.py`、`context.py` 与获批的 `llm_ops.py` 每处失败写入改用具体 `error.task_failure.*` key，异常值作为 `{error}` 原样保留。通过真实写入模拟和 `GET /api/task` 验证英文原因包含 `provider unavailable`，中文输出按 Base 原文锁定；全量与窄测通过。
- 关键决策与已否决方案：通知的 `notify_error`、日志变量保留原字符串，只有 task_status.error_message 本地化；不把失败原因折叠为通用英文提示。
- 下一步唯一动作：提交并推送 C；随后修订 B 的 Starlette 原始 detail 与 D 的 task status message 本地化。

### 里程碑 10：修订 B——保留框架原始 detail
- 当前阶段：implementing
- 本段结论：`/api` 下非 `ApiError` 的 404/405/其他错误现在保留 Starlette 的 `exc.detail`，只按状态添加顶层错误码；删除未再引用的通用错误目录文案。测试锁定 `Not Found`、`Method Not Allowed` 原文和 422 形状。
- 关键决策与已否决方案：框架错误不经目录翻译，避免无意改变 Base 默认 detail；只对自定义 ApiError 使用本地化目录。
- 下一步唯一动作：提交并推送 B；随后完成 D 的 task status message 本地化。

### 里程碑 11：修订 D——task status message 双语化
- 当前阶段：implementing
- 本段结论：`GET /api/task` 的 queued、processing、calibrating、success、failed 与未知状态 message 全部走 `api.task_status.*`；逐项验证 zh-CN 与 Base 字面量一致、en 无 CJK。C 的具体失败原因本地化继续由各写入点的 `error.task_failure.*` key 负责。
- 关键决策与已否决方案：将缺省分支也改为目录 key，避免未知状态在 en 下泄露中文；不改变 task status 字段、HTTP code 或历史数据库数据。
- 下一步唯一动作：提交并推送 D，然后运行最终窄/全量验收与 scope 检查并写完整报告。

### 里程碑 8：A 红验与 scope 批准续作
- 当前阶段：implementing
- 本段结论：A 已提交并推送；将 `tasks.py` 一处 `ApiError` 暂时改回 `HTTPException(detail=...)` 后，AST 测试按预期 AssertionError 转红并定位该行，随后只还原该行。修订 dispatch 已批准 seq 1 对 `llm_ops.py` 的 scope 扩展，可继续完成 C。
- 关键决策与已否决方案：不删除默认 422 校验异常；AST 只扫描 routes（排除 views）及 transcription service，检查调用形式而不是文本。
- 下一步唯一动作：按修订要求处理 C 的各 task_status.error_message 写入点并为具体英文原因补测试。
