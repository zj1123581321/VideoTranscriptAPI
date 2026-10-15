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
