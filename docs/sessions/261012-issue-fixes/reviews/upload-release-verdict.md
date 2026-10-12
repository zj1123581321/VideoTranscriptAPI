<!-- delegate-outcome: succeeded -->
## H0 独立审查结论

审查对象固定为 `c7dc7fcbb1727057ecf2c4d8c3f38e34d3136f72..db60c385410030fc2e34def510c3c8ab1e0e5117`，风险档位 personal。

failure-visibility: clean

**结论：通过，不阻断交付。Finding：无。** 六项 spec 的资源归属和错误可见性均由当前实现及下列状态断言覆盖；改动只调整已有 `finally` 控制流并复查目录存在性。

## Spec 逐项核对

1. **错误记录失败仍显式 HTTP 500，并清理未移交资源。** `uploads.py:399-420` 在 writer 异常后仍执行 inflight、目录、预算与 request slot 的清理；`test_upload_intake_cleanup.py:29-64` 注入 `OperationalError`，检查真实媒体目录、预算、inflight、slot 和后继 202；`:67-132` 删除真实 SQLite 行后调用原 writer，验证 rowcount=0 的 `ValueError`、HTTP 500 及相同资源终态。
2. **目录未清理时释放 slot/inflight、保留预算并报错。** `uploads.py:406-420` 先释放 inflight，清理后用 `task_dir.exists()` 检查，目录仍在时抛 `OSError`，外层 finally 仍释放 request slot，预算释放被跳过。`test_upload_intake_cleanup.py:135-163` 注入清理返回但不删文件，检查 HTTP 500、真实媒体文件仍在、保留 reservation、inflight 为零且 slot 可再次取得。
3. **成功移交后 handler 只归还 request slot，worker 持有媒体及其资源。** `uploads.py:359,407-420` 设置 `transferred=True` 后跳过 handler 的目录/inflight/预算清理并释放 slot。`test_upload_intake_cleanup.py:166-212` 经真实 HTTP、RuntimeContext、SQLite 与 runtime queue 检查回执、文件字节、worker 收到的字节、worker 开始时 inflight/预算仍持有及消费结束后的释放；既有 `test_upload_intake.py:195-285` 还覆盖连续受理。实际消费者在 `transcription.py:604-658,748-758`。
4. **receiver acquire 失败不释放未持有槽且不读 body。** `uploads.py:263-276` 在进入 finally 管辖区前对 acquire 失败返回既有 503；因此不会执行 slot release。既有 `test_upload_intake.py:425-442` 检查 503 和 body 未消费。
5. **测试保留真实边界且断言实际状态。** 新用例复用 `test_upload_intake.py:108-193` 的 FastAPI/TestClient、SQLite、RuntimeContext、TempFileManager、raw producer bytes 与 queue worker fixture。writer、rowcount 和清理故障的注入均有命中/异常判据；目录、文件字节、DB 行、reservation、inflight、slot 与 queue/worker 状态由实体断言，不以调用次数代替。
6. **文档边界与反熵。** `design.md:14-15,27-30` 明确目录无全面自动回收保证及 reservation 可能保留至重启；`:41-44` 明确不加入无 AF_UNIX 消费者依据的 108 字节预算。文档未宣称生产 pending 事故或所有目录 24 小时自愈，也未升级为 P1。diff 无新运行时抽象、状态、schema、配置、依赖、重试、fallback 或防御式 catch；header/body/receipt/DB schema 逻辑未改。

## 验证

- OCR：envelope `status=reviewed`、`cli_status=complete`、`coverage=complete`、`reason=primary_selected`、0 findings；secondary verify 因无 finding 显示 skipped，不影响主扫描已完成的状态。
- 固定 H0 窄测：`PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:. python -m pytest -q -p no:cacheprovider tests/integration/test_upload_intake_cleanup.py tests/integration/test_upload_intake.py tests/unit/test_upload_routes.py tests/unit/test_upload_dispatch.py`，在 scratch worktree 退出码 0（43 项）。另核实 cwd 与 git root、route/test 模块导入路径均在 H0 scratch；解释器 Python 3.11.15。
- Base 红验：只向 base scratch 拷入 H0 的 `test_upload_intake_cleanup.py`，运行两个 writer 用例；预期退出码 1，2 项均因未清除的真实媒体文件断言失败。rowcount 用例在相同 SQLite 状态下另以真实 writer `pytest.raises(ValueError)` 确认故障路径，非导入/配置错误。
- H0 时序变异：分别把 inflight 与预算释放移出 `not transferred` 后，`test_worker_consumption_starts_while_intake_resources_still_held` 各以退出码 1 在 pytest 主线程的真实状态断言失败（分别观测到 `0 != 1`、`False is not True`）；两次均从 H0 恢复源码并核对 diff 为空。
- H0 worker 时序用例连续五次退出码 `0,0,0,0,0`；冻结 diff 的 `git diff --check` 退出码 0。

## 未验证边界

生产上传开关、并发值与线上事故未实测，因此不作生产触发或 P1 断言。派发时主干基线查询不可用；本轮未跑 CI，继承红/新红无法判定。
