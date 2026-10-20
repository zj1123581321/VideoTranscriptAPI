# C6 面向用户文档 i18n 进度

### 里程碑 1：错误码参考生成器与入口文档对齐

- 当前阶段：implementing
- 本段结论：新增错误码 Markdown 生成脚本与防漂移测试；两版 README 的 `##`/`###` 标题逐节对应，补入最小配置、语言和 API 错误响应说明。skill 与文档中心索引已补充错误响应 / 服务端语言行为说明。
- 关键决策与已否决方案：错误码及任务失败原因文案直接读 locale，HTTP 状态由 `ApiError` AST 调用抽取；请求校验 422 与框架错误 detail 作为不同契约说明，不伪装成 locale 文案。
- 下一步唯一动作：验证 locale 变化时生成输出会令未更新的错误码参考防漂移测试失败，再运行窄测与全量测试。

### 里程碑 2：防漂移红验

- 当前阶段：implementing
- 本段结论：窄测 `uv run --frozen pytest -q tests/unit/docs` 通过；在隔离临时仓复制同一生产源码和测试，仅修改英文 locale 的一条错误文案而保留旧生成文档，执行生成文档一致性测试得到预期 `AssertionError`，确认测试能抓住 locale 漂移。
- 关键决策与已否决方案：红验只改隔离临时仓中的 locale，不改本仓 locale 文件；生成文档逐字对比是有效判据，差异具体落在 `error.invalid_url` 的文案。
- 下一步唯一动作：运行 `make test`，完成生产代码位置对照与最终 scope / 提交核查。

### 里程碑 3：验收与推送

- 当前阶段：completed
- 本段结论：`make test` 与文档窄测通过；scope 检查覆盖的 10 个文件全部匹配卡面，分支提交已推送并通过 `git ls-remote` 确认远端 tip 与本地一致。新增 Python 文件通过 `py_compile`。
- 关键决策与已否决方案：仓库没有配置或依赖静态类型检查工具；因此执行当前可用的 Python 编译检查，不额外引入工具链或依赖。
- 下一步唯一动作：将完整报告写入 `$DELEGATE_REPORT_PATH` 并按收尾流程交接。

### 里程碑 4：失败诊断保持英文

- 当前阶段：completed
- 本段结论：防漂移测试失败时改用明确的英文 `AssertionError`，避免 pytest 展开双语文档正文，符合测试 console 纯英文约束；成功路径窄测仍通过。
- 关键决策与已否决方案：不直接 `assert` 长 Markdown 字符串相等，以免断言失败时 pytest 将整份本地化文案 diff 打到 console；仍以逐字字符串相等作为判据。
- 下一步唯一动作：提交测试诊断收敛并在最终 HEAD 上重跑全量与窄测。

### 里程碑 5：最终全量验收

- 当前阶段：completed
- 本段结论：窄测通过；`make test` 首轮仅在既有集成探针 `test_local_capacity_probe_exercises_real_http_payload_and_loopback_overlap` 报 `controlled_url_download_did_not_overlap_upload_receiving`，单测独立重跑通过，随后完整 `make test` 再次通过。未改该测试或生产代码。
- 关键决策与已否决方案：将该一次性并发探针红单独记录；派发基线查询不可用，继承红无法判定，不把它归因给本卡，也不把首轮红隐去。
- 下一步唯一动作：完成 scope / 远端 tip / 干净工作区复核并写最终报告。

### 里程碑 6：错误码主表结构修复

- 当前阶段：implementing
- 本段结论：移除生成器在 Markdown 表头分隔行后插入的空行；生成结果现以数据行紧跟分隔行，新增结构断言检查分隔行后的数据行及各行列数，并验证 locale 中的竖线和换行会被转义。先在旧生成器上得到 `AssertionError` 红，再在修复后通过相关测试。
- 关键决策与已否决方案：结构约束作用于每张生成表，不只针对当前主表；locale 特殊字符用临时源目录 fixture 验证，不修改真实 locale 文案。
- 下一步唯一动作：修复任务失败说明中 `data.error` 的本地化文本语义并完成对应文档再生成。
