# 上传批次修复设计-note（2026-10-12 批，已批准的降级最小契约）

来源：2026-10-12 工程审查报告（第一性原理审计），主脑已批准其中 A/B/D 的降级方案。
本 PR 只实现 B（#204）；A、D 契约随批次另卡落地；C 延后，不在本批实现。

## B（本卡 #204）：接收失败不得短路请求槽与未移交在途资源释放

缺陷：`receive_upload` 的 finally 按「写错误记录 → 目录清理 → 预算 → inflight →
slot」顺序执行，任何一步抛异常即跳过其后全部释放。默认 `receive_concurrency`
为 1，写库或目录清理失败一次就让上传入口持续 503 直到进程重启（单点变砖）。
风险排序：slot ≫ inflight > 预算 > 目录（预算与 inflight 是内存账本、重启即清；
目录泄漏无自动回收保证——已核定定时清理仅对 receiving 记录 unlink，
不保证覆盖所有失败目录）。

契约（不变式轴）：

| 条件 | request 槽 | 未移交 inflight | 临时目录/预算 | 错误可见性 |
| --- | --- | --- | --- | --- |
| 错误记录抛 OperationalError/rowcount ValueError，清理成功 | 释放 | 释放 | 目录移除、预算归零 | 原异常上抛（HTTP 500） |
| 目录清理失败、未移交 | 释放 | 释放 | 目录保留，其已占用预算同步保留（不假报磁盘已回收） | OSError 上抛（HTTP 500） |
| 正常受理（transferred=True） | 请求结束时释放 | worker 持有并在完成后释放，handler 不夺权 | 媒体不被 handler 删除，预算不由 handler 误清 | 不适用（202） |
| receiver acquire 失败 | 未持有即不释放 | 未取得 | 未取得 | 既有 503 行为不变 |

实现：只调整 uploads.py 现有 finally 控制流——错误记录包进独立 try/finally，
其 finally 内按 inflight → 目录清理（含 exists 复查）→ 预算执行，目录仍在则
预算刻意保留；slot release 放最外层 finally。不新增重试、资源框架、生命周期
账本或错误协议；既有 header/body/receipt 语义不变。

## A（#226，另卡）：cache 合并仅在非 failed 终态清 error

只允许 {generated, skipped_short, skipped_no_timeline, disabled} 终态清除旧
error；pending 与未触碰状态保留旧 error；若 caller 写 pending 则 writer 保留
旧诊断（该场景生产路径未证实，不作宣称）。另补「FAILED→pending 时
error 仍在」用例。

## D（#216，另卡）：TMPDIR 指向 scratch 子目录

e2e 子服务 TMPDIR 改为 serverScratch/tmp 子目录（先创建），并在既有
/__e2e__/state 中断言 `tempfile.gettempdir()` 落在 scratch 之下。不引入
108 字节 socket 路径预算：API 走 TCP，未发现带路径名（bind 文件系统路径）
的 AF_UNIX 消费者，该预算缺乏真实需求。

## C（#212）：延后

转义接受范围（企微 markdown_v2、飞书 lark_md 实认集合）与 heading 其余调用方
覆盖未验证，按现稿做有引入双重编码的风险，待实测后再立项。
