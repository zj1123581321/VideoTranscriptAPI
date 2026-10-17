<!-- delegate-outcome: succeeded -->

## Verdict

审查结论：P2-only；阻断交付：是。真实 Chromium 门禁、正常失败路径的 trace 与截图保存、artifact 路径及长期政策均成立；不变式 1 的错误汇总会被前置断言短路，不变式 2 的 workflow 取消路径不会上传产物。

failure-visibility: p2-only

## Findings

### P2 — 前置断言失败时不会输出 console 与网络错误汇总（不变式 1）

- 位置：[e2e/tests/local-upload-full-chain.spec.ts:229](../../../../e2e/tests/local-upload-full-chain.spec.ts#L229)、[e2e/tests/local-upload-full-chain.spec.ts:401](../../../../e2e/tests/local-upload-full-chain.spec.ts#L401)。
- 触发：让 `POST /api/uploads` 返回 HTTP 500；第 229 行的 202 断言先抛错，末尾第 401–411 行构造并断言 `failureReport` 的代码不会运行。
- 风险：该次 Chromium 回归仍失败，trace artifact 仍可提供底层事件，但 Actions 测试失败输出不会同时列出 console 与 network 两类错误，违反不变式 1 的报告要求。
- 阻断理由：这是明确验收项；P2 来自诊断信息缺失，测试本身仍失败、没有静默放行。

### P2 — Job 到时限取消时 failure-only 上传步骤不会执行（不变式 2）

- 位置：[.github/workflows/ui-browser.yml:14](../../../../.github/workflows/ui-browser.yml#L14)、[.github/workflows/ui-browser.yml:47](../../../../.github/workflows/ui-browser.yml#L47)。
- 触发：job 的 15 分钟上限在 Chromium 回归仍运行时到期。真实 runner run `38715807063` 从 job 开始到 cancelled 约 15 分 25 秒，Chromium step 在结束前 16 秒才启动并被取消；当前固定 diff 保留同一个 job timeout，并新增 `if: failure()` 上传条件。
- 证据与机制：GitHub 对 job timeout 的定义是自动取消；取消时会重评尚未执行的 step 条件。`failure()` 仅表示之前的 step 失败，而取消由 `cancelled()` 表示，因此该上传 step 不会因取消而执行。[GitHub workflow 条件](https://docs.github.com/en/actions/reference/workflows-and-actions/expressions)、[timeout-minutes](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax)、[取消流程](https://docs.github.com/en/enterprise-cloud@latest/actions/reference/workflows-and-actions/workflow-cancellation)。
- 风险：job 以 cancelled 结束、门禁不会变绿，但该次 Chromium 现场的 trace、截图没有可下载 artifact。实际自托管 runner 已出现该时限形态；严重度 P2（证据丢失，不是静默放行），按不变式 2 阻断交付。

## 不变式核对

- 不变式 1：保留原业务断言；console、page error、请求失败与 HTTP 错误仍被观察，console 行带 location URL。前置断言绕过统一汇总见上述 finding。
- 不变式 2：Playwright `outputDir` 与 workflow 上传路径均为 `e2e/node_modules/.cache/playwright-test-results`；失败截图、失败 trace、隐藏目录与 7 天保留均有配置。普通 step failure 会上传；job timeout/cancellation 会跳过当前 `failure()` 条件，见第二条 finding。官方配置说明支持全局 `use` 作为项目共享选项，trace 模式保留失败运行：[Playwright 配置](https://playwright.dev/docs/test-use-options)、[Playwright TestConfig](https://playwright.dev/docs/api/class-testconfig)。
- 不变式 3：AGENTS.md 与浏览器测试文档声明本仓长期使用原生 Actions artifact，不接维护者私有 PWRS、不要求 token；真实 Chromium workflow 仍是阻断步骤。`include-hidden-files` 与 retention 输入符合上传 action 契约：[upload-artifact](https://github.com/actions/upload-artifact/blob/main/README.md)。
- 不变式 4：没有新增重试、服务或宽泛上传路径；`retries: 0` 保留，上传仅指向 Playwright 的实际 `outputDir`。

## 验证与基线

- OCR 前置扫描：`status=reviewed`。工具标注 cancellation 风险为 High，本仓按真实用法重定为 P2：近期 50 次 workflow 中的取消 run `38715807063` 全 job 用时约 15 分 25 秒，且 Chromium step 正在运行，吻合 15 分钟 job 上限；该路径真实存在。若触发，门禁保持 cancelled/非绿，但产物缺失只影响诊断，故不是 P1。精确 H0 run `39002966220` 的 Chromium job 成功，运行约 3 分 51 秒。Playwright 的 180 秒单测超时覆盖普通用例挂起，但不能覆盖本次实测的 setup 耗时挤占整个 job 预算。
- OCR 对“上传路径重复”意见被当前 config、npm 调用路径及精确 H0 成功运行证伪；设备字段顺序意见无当前行为证据，均未登记为 finding。
- 任务卡所给主干基线不可用，故继承红未能判定；本次没有运行测试或触发新 CI，因此没有本卡新红。已读取精确 H0 的既有 workflow run：Vitest 与 Chromium 步骤成功，artifact 步骤按成功路径跳过。另将旧 run `38715807063` 的取消记录作为当前自托管 runner 的环境证据，不把它归为本卡新红。
- 窄验证 `git diff --check` 通过；本 verdict 是本分支唯一新增文件。
