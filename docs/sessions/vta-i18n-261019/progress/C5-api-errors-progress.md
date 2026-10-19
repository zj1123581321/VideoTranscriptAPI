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
