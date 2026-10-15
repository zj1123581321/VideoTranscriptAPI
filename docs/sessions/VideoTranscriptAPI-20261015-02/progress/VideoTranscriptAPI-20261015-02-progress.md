# VideoTranscriptAPI-20261015-02 progress

## 2026-10-16 里程碑1：BusyLock 模块与受理/终态挂接

### 当前阶段
implementing：生产代码与 `tests/unit/test_busy_lock.py` 已落地，narrow verify 全绿。

### 本段结论
服务侧忙锁按卡面锁定决策落地：`BusyLock.acquire()` 非阻塞共享 flock；拿不到返回 False，POST `/api/transcribe` 在 `create_task` 之前拒绝并 HTTP 503；入队成功后按 task_id 持独立 fd，终态入口 `finalize_terminal_status_and_notify` 释放。compose 种子增加 `./.deploy-state:/app/.deploy-state`。既有 `tests/unit/test_api_routes.py` 零改动通过。

### 关键决策与已否决方案
- 挂接点：受理只改 `api/routes/tasks.py` 的 `transcribe_video`（create_task 之前）；释放只挂 `api/services/terminal_status.py` 的终态唯一入口。orphan recovery 走 cache_manager 直写 update_task_status，不经该入口，符合「旧进程遗留任务不加锁也不释放」。
- fd 映射用 `dict + threading.Lock`（`acquire_for_task` / `release_for_task`），每任务独立 BusyLock 实例。
- 否决：抽出 `_finalize_terminal_status_body` 包装函数（单消费者抽象，已撤，改为原函数 try/finally）。
- 否决：给 recalibrate/resummarize 也加锁（卡面只锁定 POST /api/transcribe）。

### 下一步唯一动作
先 commit 本段真修复，再做「acquire 在 LOCK_EX 下改返回 True」红验，然后 `make test`。

## 2026-10-16 里程碑2：红验转红 + make test 仅继承红

### 当前阶段
implementing 收尾：红验已还原，准备 push PR #246。

### 本段结论
红验只改 BusyLock.acquire 的 BlockingIOError 分支 `return False` → `return True`：`test_exclusive_holder_makes_acquire_return_false` 断言失败 `assert True is False`；HTTP 用例 `assert 200 == 503`。类型是 AssertionError。还原该一行后 working tree 与 HEAD 一致。`make test` 4003 collected，唯一失败为继承红 `test_asr_monitor_alert_delivery.py::TestNetworkGuard::test_unix_domain_socket_is_not_blocked`（AF_UNIX path too long），无新红。

红验原文：
```
E   assert True is False
E    +  where True = acquire()
```
```
E   assert 200 == 503
E    +  where 200 = <Response [200 OK]>.status_code
```

### 关键决策与已否决方案
无。

### 下一步唯一动作
commit 本段 progress，push fast-forward 到 origin/card/VideoTranscriptAPI-261015-d3，写报告。

## 2026-10-16 里程碑3：gate primary 第 3 轮裁决落地

### 当前阶段
implementing：第 3 轮两条 finding 已按主脑裁决落盘，待 yaml parse / Accept-Check / push。

### 本段结论
①reliability-deploy-during-active-task 拆两半：(a) 挂载静默降级改为 fail-loud——deploy.yml 在 ship 成功后新增 `verify-busy-lock-inode`，同一 host/key/deploy_dir 对账宿主与容器 `busy.lock` 的 `stat -c %i` inode，任一失败 job failure；(b) 首次自动部署空档不入码，PR 正文答辩（旧容器无 BusyLock，物理不可消；缓解=主脑 workflow_dispatch + #249 确认非终态任务为 0）。②design-production-latest-policy-contradiction：README 区分 registry 可变 tag 禁令与部署机本地 `video-transcript-api:latest` retag 别名。

### 关键决策与已否决方案
- 验证做成 ship 的 sibling job，而非改 ci-templates：caller 无法向 reusable workflow 插入步骤；跨仓改 ci-templates 禁止。因此对账发生在健康探针之后、workflow 成功之前（新 SSH 会话，同一身份）。否决「把 build-deploy.yml 内联进本仓」——无第二消费者的复制。
- ssh_user 不写进本公开仓：运行时从 ci-templates v2 的 input default 解析，避开 public-scan 身份字面量。
- 否决「inode 对账失败只打 warning」——主脑明确 fail-loud。

### 下一步唯一动作
跑 yaml parse 与 Accept-Check，commit 本段，push 更新 PR #246 正文 findings 处置节。
