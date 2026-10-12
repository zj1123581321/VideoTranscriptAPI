# upload-release（#204）进度存档

派发：dlg-20261012-112410-ebc035；分支 card/vta-261012-upload-release；base c7dc7fcb。

## 阶段：repairing

### 2026-10-12 第 1 段：批准设计落盘
- 本段结论：现场核查通过（worktree 干净、origin/main=base）；已批准的 A/B/D 降级契约落 `docs/sessions/261012-issue-fixes/design.md`，本卡只实现 B（#204）。
- 关键决策：采用「错误记录独立 try/finally + inflight 提前到目录清理之前 + slot 放最外层 finally」结构；目录仍在时预算刻意保留（字节真实占盘，不假报回收）。
- 已否决方案：吞掉 writer 异常继续走（违反 fail-fast）；为清理失败补重试/资源框架（超范围，无第二消费者）。
- 下一步唯一动作：新增 `tests/integration/test_upload_intake_cleanup.py`（复用既有真实 fixture），在原实现上验红（AssertionError 因资源未释放）。
