# 独立复审结论：部署信号测试候选身份契约（#237）

- 结论：PASS；risk-tier personal。
- 固定审查范围：`c7dc7fcbb1727057ecf2c4d8c3f38e34d3136f72..75d5f4df53e03d2966b6fc1f3e3508133c06a1d2`，目标文件 55 行新增、16 行删除；增量 `3953154805704284d5436a87a624e0bf1b8991cb..75d5f4df53e03d2966b6fc1f3e3508133c06a1d2` 为 3 行新增、1 行删除。
- 四问：①仅修登记的候选身份 finding，是；②新增抽象，无；③无依据新增状态、事实源或 fallback，无；④双路径，无。

## 不变式与证据

- `tests/deployment/test_pull_and_deploy.py:185-260` 用候选完整 digest 与旧 digest分别核对两条实际 compose up 日志；候选 up 后须出现健康探测，TERM 后第二条 up 为旧 digest，最终状态仍为旧值。
- `tests/deployment/test_pull_and_deploy.py:13-58` 的 fake Docker 记录消费到的 `VIDEO_TRANSCRIPT_IMAGE` 环境值和 argv，并从健康状态文件返回真实状态；`docker/pull_and_deploy.sh:188-216,255-285` 是被测 producer 与回滚消费者。
- 正常路径实测事件为候选 up → `starting` 健康结果 → 旧 digest up → `healthy` 结果；恰 2 次 up、3 次探测，部署子进程 rc=143，`.deploy-image` 原始 bytes 为旧 digest 加 LF。测试断言 rc、顺序、数量、旧状态及候选/回滚错误信息缺失。
- 活性上界为两次 5 秒日志等待及 `communicate(timeout=15)`；日志等待失败时 `kill()` 后 `communicate()` 回收直接子进程。正常子进程由 `communicate()` 回收。
- 直接消费者检查：部署脚本由目标测试通过 `SCRIPT` 实际调用；`tests/deployment/test_healthcheck_route.py` 读取该脚本的 fallback 探针并与 Dockerfile 路由比对。

## 负对照与结论

- 首次 `deploy_digest(CANDIDATE_DIGEST)` 改为 `OLD_DIGEST`：完整 `docker/` 目录在仓外副本中改动并由复制测试实际消费。H0 绿（1 passed；首次 up 为旧 digest）；H1 按目标测试 `AssertionError: candidate health probe did not run` 红（pytest rc=1；部署子进程 -9；仅 1 次旧镜像 up；状态保持 starting 和旧 digest）。这不是配置、模板或导入错误，也未达到 30 秒健康超时。
- 删除测试 TERM：目标断言因旧镜像 rollback up 未发生而红；子进程 -9、1 次候选 up、状态 starting、状态文件旧值。
- 删除生产 TERM trap：同一目标断言红；子进程 -15、1 次候选 up、状态 starting、状态文件旧值。
- 提前忽略 TERM：同一目标断言红；子进程 -9、1 次候选 up、状态 starting、状态文件旧值。三项均在健康检查预算内结束。
- 独立 H1 scratch 全文件 19 passed；候选信号目标重复 5 次全部通过。登记 P2 finding 已由 H1 身份断言修复；新增未解决 findings：0（P1=0，P2=0，P3=0）。AC 不阻断：候选身份负对照在 H0/H1 呈现绿/红分离；P2 不自动等于 P1。
- OCR stdout JSON：`status=skipped`、`reason=no_reviewable_items`、`coverage=none`、退出码 0；按 skipped 记，未重跑，不能视为 clean。独立全量审查与 scratch 验证已完成。
- CI run/job 结论未核验；卡面所述主干基线 API 请求失败，继承红状态无法判定；原 CI 时序及 PR draft/ready 状态未知。本结论不声称产品 CI 绿。

failure-visibility: clean
