<!-- delegate-outcome: succeeded -->

# 上传全链临时目录隔离审查

- **审查对象**：`c7dc7fcbb1727057ecf2c4d8c3f38e34d3136f72..c3fbf5d35e1f768eb8757c1568c47089744272cf`；固定 H0，risk-tier personal；3 文件，15 行。
- **代码结论**：通过；无 P1/P2/P3 finding，产品变更不阻断。
- **父实现验收**：阻断。现有 precheck 的合成主干浏览器 Verify-Command 红在缺少 `@playwright/test`，详见下文；这是验收环境红，不作代码 finding 或豁免。
failure-visibility: clean

## 静态审查

- OCR：`ocr-review` envelope `status=reviewed`、`findings=[]`；clean。
- `e2e/tests/local-upload-full-chain.spec.ts:134-145` 在 server 子进程启动前创建 `serverScratch/tmp`；`:51-70` 的 `spawnEnv.TMPDIR` 实际传给 `spawn`，cwd 与脚本 argv 指向本轮 repo。
- `tests/local_upload_real_server.py:114-153` 的测试专用 `/__e2e__/state` 返回 `tempfile.gettempdir()`；浏览器读取实际 JSON 并断言等于 parent 已知路径且不等于 `/tmp`。
- 全链原有字节 SHA、上传记录唯一性、单个 ASR frame、LLM/通知 payload、history/read/revoke 与空网络错误集合断言保留；原 `afterAll` 释放 ASR、SIGTERM 和 `rm` 清理保留。
- 本轮 diff 仅 3 个指定文件，共 12 additions / 3 deletions；未引入产品端点或额外运行机制。

## 验证

- 隔离环境：scratch helper 固定 H0；`uv sync --frozen` 和 `npm ci` 使用锁文件；venv 与 `e2e/node_modules` 均为 scratch 私有实体。Python prefix、`video_transcript_api.__file__` 与 server 脚本 `__file__` 均落在 scratch。主仓 venv shebang 检查无 `/tmp` 污染。
- 窄浏览器命令：`cd e2e && VTA_BROWSER_PORT=<动态 loopback 端口> npx playwright test tests/local-upload-full-chain.spec.ts --workers=1`，退出码 0，`1 passed`。
- 负对照：scratch H0 只把 spawn 的 `TMPDIR` 改成 `/tmp`，目标测试退出码 1；API 响应实值 `/tmp` 与期望 scratch `tmp` 不同，断言转红。逐行恢复后 `git diff` 对 H0 为空。
- 类型对照：base 与 H0 使用相同消费者目录、CPython 3.11.15 私有 venv、TypeScript 5.6.3、Pyright 1.1.408。TS 命令 `npx --yes --package typescript@5.6.3 tsc --noEmit --pretty false -p e2e/tsconfig.json` 两边均退出 2，唯一 TS2322 为既有 `spawn` stdin 类型诊断。Pyright 命令 `PYTHONPATH=src:tests/fixtures uvx --from pyright==1.1.408 pyright --pythonpath .venv/bin/python --outputjson tests/local_upload_real_server.py` 两边均退出 1，唯一 `reportOptionalMemberAccess` 集合相同，行号 139→140 随插入行移动；无新增诊断。

## 父实现验收

- 命令：`accept_precheck.py --dispatch-id dlg-20261012-160714-609acc --repo-path <主仓路径> --commit-range c7dc7fcbb1727057ecf2c4d8c3f38e34d3136f72..c3fbf5d35e1f768eb8757c1568c47089744272cf`；precheck 退出 2。
- 完整 JSON：delegate state 中 `20261012-160728-frontend-cursor-VideoTranscriptAPI/accept_precheck.json`；dispatch `dlg-20261012-160714-609acc`，task `VideoTranscriptAPI-20261013-02`，H0=`c3fbf5d`，检查时 main=`c7dc7fc`。
- 主结果 `status=red`：`verify_on_merged_main=red`，`npm run test:browser` 退出 1；合成 worktree 找不到 `@playwright/test`，`npx` 尝试安装 `playwright@1.63.0` 后配置加载失败。全 17 个浏览器用例未收集/未验证；按卡面只执行这一次，不重跑或改参。
- Advisory：`scope=green`；`accept_check=green`（1 条）；`report_claims=red`（缺标题“闸与绕过，与卡面的偏差”）；CI 记录 green 但 gate primary / shadow 等均 skipped，不能视作完整 CI。
- 派发时主干基线不可用（`gh api request failed`），该 precheck 红无法归为继承红或新红。

## Findings 与阻断

- Findings：无；failure visibility 为 `clean`。浏览器行为符合 spec，且单点 `/tmp` 变异能触发目标断言。
- 本次代码审查不阻断。父实现 accept-precheck 仍红，父实现验收保持阻断。
- 录屏例外行 `AGENTS.md:3` 于 2026-10-08 写入，尚在 90 天内；它只豁免录屏发布，不豁免本次已执行的真浏览器行为验证。

## 与卡面的偏差及未验证项

- 现有 `playwright.config.ts` 要求 `VTA_BROWSER_PORT`；裸 `npx playwright test` 会在配置载入前退出。窄测按 `run-browser-tests.mjs` 的动态 loopback 端口分配，在 `e2e/` cwd 执行同一发现器和 spec。
- 父 precheck 的完整浏览器套件未能进入测试收集；除此之外未重复全量入口。未验证 full 17-suite 结果及完整 CI/gate 状态。
