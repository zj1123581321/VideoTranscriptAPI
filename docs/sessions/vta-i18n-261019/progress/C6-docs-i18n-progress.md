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

### 里程碑 7：任务失败响应语义明确

- 当前阶段：implementing
- 本段结论：错误码参考明确说明 `data.error` 是失败时写入的本地化文本，不是 locale key；其内容可变、不稳定且不能用于客户端分支，表中 key 仅作文案查找。skill API 参考同步澄清，新增生成文案断言并重生成文档，文档窄测通过。
- 关键决策与已否决方案：不扩改 README 中只描述 task failure reasons 的概括句，因为没有把 key 误作响应值；只修正明确讨论 `data.error` 的表述。
- 下一步唯一动作：令生成器对扫描到的非字面量 `ApiError.error_code` 调用 fail-closed 并覆盖关键字调用形态。

### 里程碑 8：ApiError AST 抽取 fail-closed

- 当前阶段：implementing
- 本段结论：AST 抽取新增关键字参数支持，并对扫描到的缺失或非字符串字面量 `error_code` 抛出带文件名和行号的错误；fixture 测试锁定关键字调用抽取及变量调用报错。修复前两项测试均以 `AssertionError` 变红，修复后文档窄测与 Python 编译检查通过。
- 关键决策与已否决方案：保留状态码表达式的既有展示方式，位置形式继续使用第二个参数，并兼容 `status_code` / `error_code` 关键字形式；不对无法确定错误码的调用静默忽略。
- 下一步唯一动作：检查最终差异与范围，运行要求的窄测和 `make test` 并按顺序提交推送。

### 里程碑 9：续修验收与推送

- 当前阶段：completed
- 本段结论：`uv run --frozen pytest -q tests/unit/docs` 退出码 0（9 项通过），`make test` 退出码 0（全套收集进度到 100%，3 项跳过）；新增 Python 文件通过 `py_compile`，`git diff --check` 与卡面 scope 检查通过。前三项修复按结构断言、响应语义、AST fail-closed 顺序分别提交并逐次推送，远端每步均经 `git ls-remote` 核实。
- 关键决策与已否决方案：pytest 的双重 quiet 配置未输出总数，仅报告实际进程退出码与进度输出；不为未配置的类型检查工具引入依赖，使用仓内可用验证与编译检查。
- 下一步唯一动作：提交本段进度与最终验收报告，并复核远端 tip 和工作区状态。

### 里程碑 10：`data.error` fallback 语义校准

- 当前阶段：completed
- 本段结论：逐行核对 `get_task_status` 后，将生成文档与 skill 说明细化为「失败文案文本，通常在失败写入时按服务端语言本地化；无存储文案时使用当前语言的通用失败文案」，并明确非 locale key、不稳定、不可分支；最终窄测 9 项通过。最终再次运行 `make test` 时，唯一失败为 `test_local_capacity_probe_exercises_real_http_payload_and_loopback_overlap`，错误为 `controlled_url_download_did_not_overlap_upload_receiving`。
- 关键决策与已否决方案：不把 fallback 描述成持久化文案，因为 `tasks.py:547` 在缺失 `error_message` 时调用当前语言的 `error.task_failed`；全量探针红与进度里程碑 5 记录的同一失败标识一致，但派发基线不可用，继承红仍标为未能判定。
- 下一步唯一动作：提交这次准确性补充，完成最终 scope、远端 tip 与工作区核验并写报告。
