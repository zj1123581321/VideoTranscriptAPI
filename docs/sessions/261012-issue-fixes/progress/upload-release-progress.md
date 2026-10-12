# upload-release（#204）进度存档

派发：dlg-20261012-112410-ebc035；分支 card/vta-261012-upload-release；base c7dc7fcb。

## 阶段：repairing

### 2026-10-12 第 1 段：批准设计落盘
- 本段结论：现场核查通过（worktree 干净、origin/main=base）；已批准的 A/B/D 降级契约落 `docs/sessions/261012-issue-fixes/design.md`，本卡只实现 B（#204）。
- 关键决策：采用「错误记录独立 try/finally + inflight 提前到目录清理之前 + slot 放最外层 finally」结构；目录仍在时预算刻意保留（字节真实占盘，不假报回收）。
- 已否决方案：吞掉 writer 异常继续走（违反 fail-fast）；为清理失败补重试/资源框架（超范围，无第二消费者）。
- 下一步唯一动作：新增 `tests/integration/test_upload_intake_cleanup.py`（复用既有真实 fixture），在原实现上验红（AssertionError 因资源未释放）。

### 2026-10-12 第 2 段：TDD 红验与最小修复
- 本段结论：新增回归 3 例（复用既有真实 upload_client/_post/_key 与真实 SQLite/TempFileManager/inflight/worker，只导入不改原文件）。原实现上行1红：`AssertionError: 接收目录必须已被清理`（writer 抛OperationalError 后目录/预算/inflight/槽全部泄漏，HTTP 500）；行2红：`AssertionError: 未移交inflight必须已释放 assert 1 == 0`（目录 exists 复查抛OSError 后预算保留正确但 inflight/槽泄漏）。行3原实现即绿（移交路径未破坏）。修复后窄回归 4 文件 41 passed exit=0；新文件连续 5 次退出码 0,0,0,0,0。
- 关键决策：只重构 uploads.py 现有 finally——错误记录包独立 try/finally，inflight 提前到目录清理之前，slot 放最外层 finally；目录仍在则预算刻意保留（不假报回收）；未新增重试/框架/错误协议。故障注入全部在 fixture 域（monkeypatch 实例方法），注入命中用调用计数证明、资源断言全部读真实状态。
- 已否决方案：延迟捕获再重抛 writer 异常（嵌套 try/finally 顺序即可达成，少一层状态）；patch Path.unlink/shutil.rmtree 注入清理故障（目标不精确，clean_up_task 实例域更准）。
- 下一步唯一动作：最小变异红验（打回 writer-before-release 顺序），随后全量 make test + pyright。

### 2026-10-12 第 3 段：变异红验、全量与类型检查（收尾）
- 本段结论：变异红验成立——仅把错误记录打回释放前位置（writer-before-release），行1用例转红 `AssertionError: 接收目录必须已被清理`；还原该处后窄回归复绿 41 passed exit=0。全量 `TMPDIR=/tmp/vta-B-suite.QgGFIJ make test` 进度到 [100%]、退出码 0（收集约3908例，日志仓外 /tmp/vta-B-full-suite.log）；新窄回归连续5次退出码 0,0,0,0,0。pyright：修复版与 base 版同为同一批 7 个既有错误（仅行号随 hunk 偏移），未新增类型错误。tests/README.md 的 B 接收回归命令清单跟改新文件（Scope-Follow）。
- 关键决策：tests/pytest-test-durations.json 仓内不存在且无消费者，不新造；全量用独立短 TMPDIR 隔离本机 AF_UNIX 环境噪声（#3825，非 #216）。
- 已否决方案：等远端 draft CI 再收尾（卡面明确不作执行器完成条件）。
- 下一步唯一动作：推送文档跟改提交，交主脑验收。

### 2026-10-12 第 4 段：feedback 补齐（dlg-20261012-120624-077823）
- 本段结论：补 rowcount ValueError 真实 writer 路径回归（不变式行1第二分支）：fixture 域包装 set_local_upload_receiving_path——先真实调用原方法、再真实 SQLite DELETE 删记录，令 finally 内真实 set_local_upload_error 的 UPDATE rowcount=0 自身抛 ValueError；不替身冒充 writer。测试内 sanity 直接调真实 set_local_upload_error 断言 ValueError（注入有效性同状态证明）；HTTP 500（非 400 静默）、目录清/预算零/inflight 0/槽可再获取/后继 202 全部锁死。变异红验：仅把错误记录打回释放前位置，新用例转红 AssertionError（见报告原文）；还原后复绿。design 三处事实收紧（目录无自愈保证、pending 场景不作生产宣称、AF_UNIX 预算依据改写）。
- 关键决策：注入点选 set_local_upload_receiving_path（writer 前最后一个真实库调用，其后到 writer 之间产品代码无其他查库路径），注入自限一次只命中被测请求、不波及后继；首版全局包装误伤后继请求已修正。
- 已否决方案：替身直接 raise ValueError（feedback 明确不接受）；wrapper 里 patch rowcount（那不是真实 writer 路径）。
- 下一步唯一动作：commit+push，更新报告给新最终 SHA 等主脑冻结独立 review。

### 2026-10-12 第 5 段：transfer 账本不被 handler 误释放回归（dlg-20261012-135924-bf492d）
- 本段结论：Opus 验收前复核通过、生产代码零改动。新增 worker 消费起点回归：包装 transcription.process_transcription 入口采样 (task_id, inflight.size, task_id in _upload_reserved_bytes) 后调用 fixture 原 fake，主线程经 worker_results.get 确认采样后断言 (该task, 1, True)。变异红验两处各一次：inflight.release 移出 not transferred → AssertionError assert 0 == 1；release_upload_temp 移出 not transferred → AssertionError assert False is True；均 edit 逆向精确还原，uploads.py 对 HEAD diff 为空。新用例连续 5 次绿（0,0,0,0,0），四文件窄测 43 passed（42+1）。design 缺陷段改「receive_concurrency 配置为 1 时」，实现段预算保留精确注明（目录可能随后被 sweep、reservation 偏保守保留至重启，不加对账/回收机制）。
- 关键决策：采样在 fixture fake 外层包装（复用 fixture 真 asyncio.Queue + 同 loop consumer 的既有时序），断言全部在 pytest 主线程；未新增事件开关/通用 helper/fixture 框架。
- 已否决方案：在后台 worker 内 assert（异常只进日志或 queue 超时，不可靠）；为 sampling 新建独立 fixture（无第二消费者）。
- 下一步唯一动作：push 后交主脑冻结最终 H0 独立 review。
