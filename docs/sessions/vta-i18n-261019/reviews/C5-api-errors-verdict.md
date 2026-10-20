# C5 API 错误响应 i18n 审查 verdict

failure-visibility: p2-only

## 裁决

**FAIL，阻断交付。** 固定审查区间为 `341dc874e894408bded13490c73b4e9aea221418..927e2839305f6cdea47cb88e42f7bc3e60746744`。发现 3 条 P2 契约违例，另有 1 条 P3 清理项；没有 P1。P2 严重度与交付阻断分别判定：前三条因直接违反 C5 契约而阻断交付。

## Findings

### C5-1：自定义 422 错误缺少 error_code（P2，阻断）

- **位置：** `src/video_transcript_api/api/routes/audit.py:121`；测试扫描在 `tests/unit/i18n_api/test_error_codes.py:142`。
- **契约：** 契约 1、4；spec「方案要点」第 7 条。这里只豁免 FastAPI 自动生成的请求校验 422；`_normalize_history_status()` 是应用手工抛出的业务错误，仍须本地化并附稳定错误码。
- **触发：** `GET /api/audit/history?source=upload&status=bogus`。
- **复现命令：**

  ```text
  PYTHONPATH=src uv run --frozen python - <<'PY'
  from fastapi import FastAPI
  from fastapi.testclient import TestClient
  from unittest.mock import MagicMock
  import video_transcript_api.i18n as i18n
  i18n.get_language = lambda: "en"
  from video_transcript_api.api.context import install_api_error_handlers
  from video_transcript_api.api.routes import audit
  from video_transcript_api.api.services.transcription import verify_token
  audit.audit_logger = MagicMock()
  app = FastAPI(); install_api_error_handlers(app); app.include_router(audit.router)
  app.dependency_overrides[verify_token] = lambda: {"user_id": "u", "api_key": "k"}
  response = TestClient(app).get("/api/audit/history?source=upload&status=bogus")
  print("status=", response.status_code)
  print("body=", response.json())
  PY
  ```

- **实测：** 在 `language=en` 下经 TestClient HTTP 序列化，返回 `422`，body 为 `{'detail': 'status must be one of: success, failed, all'}`，没有 `error_code`。因此所有 JSON API 错误的统一形状不成立，按 `error_code` 分支的客户端无法处理此错误。
- **测试缺口：** `test_json_api_sources_do_not_call_http_exception` 只识别 AST 名称恰为 `HTTPException` 的调用。该调用被导入别名 `FastAPIHTTPException`，扫描通过；默认 422 测试也没有覆盖这个手工异常。

### C5-2：任务路由写入的失败原因仍为中文（P2，阻断）

- **位置：** `src/video_transcript_api/api/routes/tasks.py:391,453,806,880,897,1113,1176,1187,1446,1458`；写入透传点为同文件 `:200`。
- **契约：** 契约 5；spec「方案要点」第 7 条。失败原因须在 `task_status` 写入时按当前语言本地化，并保留异常原因。
- **触发：** `language=en`，transcribe / recalibrate / resummarize / notes 路由在队列已满、入队异常或格式化失败后执行 `_fail_task_after_creation()`。这 10 个调用点传入中文字符串或中文固定前缀加异常文本；helper 将其原样写入 `error_message`。后续 `GET /api/task/{task_id}` 原样回显该字段。
- **复现命令：**

  ```text
  PYTHONPATH=src uv run --frozen python - <<'PY'
  from fastapi import FastAPI
  from fastapi.testclient import TestClient
  from unittest.mock import MagicMock
  import video_transcript_api.i18n as i18n
  i18n.get_language = lambda: "en"
  from video_transcript_api.api.context import install_api_error_handlers
  from video_transcript_api.api.routes import tasks
  from video_transcript_api.api.services.transcription import verify_token
  written = {}
  def capture(*args, **kwargs):
      written.update(kwargs); return True
  tasks.finalize_terminal_status_and_notify = capture
  tasks._fail_task_after_creation("probe-task", "任务队列已满，提交被拒绝", log_context="probe")
  message = written["error_message"]
  cache = MagicMock()
  cache.get_task_by_id.return_value = {"task_id": "probe-task", "status": "failed", "error_message": message, "view_token": "v"}
  tasks.cache_manager = cache; tasks.audit_logger = MagicMock(); tasks.logger = MagicMock()
  app = FastAPI(); install_api_error_handlers(app); app.include_router(tasks.router)
  app.dependency_overrides[verify_token] = lambda: {"user_id": "u", "api_key": "k"}
  response = TestClient(app).get("/api/task/probe-task")
  print("written_error_message=", message)
  print("status=", response.status_code)
  print("body_error=", response.json()["data"]["error"])
  PY
  ```

- **实测：** 在 H0 代码上调用实际 `_fail_task_after_creation()`，捕获其传给终态写入的值，再经生产 tasks router 的 TestClient 读取：`written_error_message=任务队列已满，提交被拒绝`、`status=200`、`body_error=任务队列已满，提交被拒绝`。固定中文未转换；异常型条目也会保留中文前缀。
- **阻断理由：** 英文配置的任务失败状态仍显示中文，违反写入时本地化契约。服务没有崩溃，故定 P2。

### C5-3：终态通知重试使用了本地化的 task_status 文案（P2，阻断）

- **位置：** 写入本地化文案的 `src/video_transcript_api/api/services/transcription.py:790-794,915-919`、`src/video_transcript_api/api/services/llm_ops.py:300-304,1015-1023` 与 `src/video_transcript_api/api/context.py:1809-1811`；outbox 写入在 `src/video_transcript_api/cache/cache_manager.py:3113-3116`，重试组装在 `src/video_transcript_api/api/services/terminal_status.py:480-499`。
- **契约：** 契约 5：日志和通知文案保持原样，只有持久化到 `task_status` 的原因按语言本地化。
- **触发：** `language=en`，终态通知首次发送未获接受，随后由 dispatcher 重试。`task_terminal_notifications` 仅持久化 `task_status.error_message`；`_compose_dispatcher_error()` 重试时从 outbox 的 `error_message` 取文案，完全没有原 `notify_error` 可用。即使调用者像 `llm_ops.py` 与 `context.py` 那样为即时通知显式传了原中文 `notify_error`，重试仍会改发英文持久化文案。另有 transcription 的两处终态写入没有传 `notify_error`，因此首次通知也会直接回退到英文 `error_message`（`terminal_status.py:182`）。
- **复现命令：**

  ```text
  PYTHONPATH=src uv run --frozen python - <<'PY'
  import json
  import tempfile
  from unittest.mock import MagicMock
  from unittest.mock import patch
  from video_transcript_api.api.services.terminal_status import finalize_terminal_status_and_notify, deliver_pending_terminal_notifications
  from video_transcript_api.cache.cache_manager import CacheManager
  from video_transcript_api.utils.task_status import TaskStatus
  with tempfile.TemporaryDirectory(prefix="c5-outbox-") as cache_dir:
      cache = CacheManager(cache_dir=cache_dir)
      task_id = cache.create_task(url="https://example.com/probe")["task_id"]
      cache.update_task_status(task_id, TaskStatus.PROCESSING)
      router = MagicMock()
      router.notify_task_status.side_effect = [{"wechat": False}, {"wechat": True}]
      with patch("video_transcript_api.api.services.terminal_status._resolve_view_url", return_value=None):
          finalize_terminal_status_and_notify(
              task_id, TaskStatus.FAILED,
              error_message="Failed to submit the task: provider unavailable",
              notify_error="提交任务失败: provider unavailable",
              cache_manager=cache, router=router,
          )
          with cache._get_cursor() as cursor:
              cursor.execute("SELECT error_message FROM task_terminal_notifications WHERE task_id = ?", (task_id,))
              persisted = cursor.fetchone()["error_message"]
          print("inline_error=", json.dumps(router.notify_task_status.call_args_list[0].kwargs["error"], ensure_ascii=True))
          print("outbox_error=", json.dumps(persisted, ensure_ascii=True))
          print("retry_sent=", deliver_pending_terminal_notifications(cache, router=router))
          print("retry_error=", json.dumps(router.notify_task_status.call_args_list[1].kwargs["error"], ensure_ascii=True))
      cache.close()
  PY
  ```

- **实测：** 真实 `CacheManager` SQLite outbox 与生产 finalize/dispatcher 输出：`inline_error="\u63d0\u4ea4\u4efb\u52a1\u5931\u8d25: provider unavailable"`；`outbox_error="Failed to submit the task: provider unavailable"`；`retry_sent=1`；`retry_error="Failed to submit the task: provider unavailable\ncompleted_at=2026-10-19 20:48:47"`。首次即时通知用原文，重试从持久化文案重建，已违反通知文案不变契约。
- **即时路径：** `transcription.py:790-794,915-919` 将 `t(...)` 结果传作 `error_message`，没有提供 `notify_error`；`terminal_status.py:182` 因而让首次通知也直接回退到本地化文案。
- **阻断理由：** 通知文案变化是明确禁止项；发生在发送失败后的后续尝试，不涉及数据丢失或崩溃，定为 P2。

### C5-4：uploads._reject 现为测试专用死代码（P3，不阻断）

- **位置：** `src/video_transcript_api/api/routes/uploads.py:180`；唯一调用在 `tests/unit/test_upload_routes.py:23`。
- **契约：** 反熵条款要求新增或保留抽象有第二个生产消费者，或说明单消费者仍必要。
- **触发：** 当前所有上传路由已直接抛 `ApiError`；全仓搜索只找到 `_reject` 定义和该测试调用，没有生产调用方。测试因直接调用它而继续通过，不能证明线上上传路由在使用该 helper。
- **检索命令：** `rg -n '\b_reject\b' src tests`；输出只有 `src/video_transcript_api/api/routes/uploads.py:180` 的定义和 `tests/unit/test_upload_routes.py:23` 的测试调用。
- **严重度及阻断：** P3，纯维护负担，不影响本次响应行为；接受不修并记 backlog。

## 基线枚举与契约核对

### Base HTTPException 清单

Base AST 枚举共 74 处（`views.py` 排除）：

| 文件 | 数量 | Base 行号 |
|---|---:|---|
| `api/routes/audit.py` | 20 | 120, 170, 183, 211, 230, 241, 267, 359, 362, 583, 586, 589, 679, 682, 685, 882, 886, 916, 918, 984 |
| `api/routes/tasks.py` | 46 | 115, 125, 225, 286, 305, 399, 460, 500, 536, 598, 661, 667, 673, 704, 710, 741, 775, 811, 883, 899, 959, 965, 971, 992, 998, 1007, 1039, 1071, 1113, 1174, 1184, 1233, 1238, 1243, 1266, 1272, 1277, 1288, 1295, 1301, 1329, 1391, 1397, 1406, 1457, 1468 |
| `api/routes/uploads.py` | 4 | 181, 430, 442, 444 |
| `api/routes/users.py` | 1 | 29 |
| `api/services/transcription.py` | 3 | 585, 590, 596 |

其余业务调用均改为显式 `ApiError`。`audit.py` 的自定义 422 是唯一仍以别名 `FastAPIHTTPException` 抛出的调用；它没有 `error_code`，见 C5-1。未发现由中文显示文案反查错误码的实现。

### Base task_status 失败原因写入/透传清单

直接写入或经终态 helper 透传共 21 处：`routes/tasks.py` 11 处（Base 行 198、392、453、804、876、892、1106、1167、1177、1449、1460；其中 198 是实际写入 helper，另 10 处是其调用方）；`services/transcription.py` 7 处（646、709、779、901、972、1177、2737）；`services/llm_ops.py` 2 处（297、1008）；`api/context.py` 1 处（1762）。此外，Base 的 transcription `_fail_task_and_notify()` 有 14 个具体失败原因调用点（Base 行 1994、2034、2099、2181、2242、2248、2342、2466、2473、2483、2491、2497、2621、2643）。H0 将这些调用点逐一改为传 `task_status_error=t(...)`；对应 locale key 在 `_TASK_FAILURE_BASE_DETAILS` 中有硬编码 Base 期望。transcription、llm_ops、context 的直接持久化文案也改为 `t()`；仅 `routes/tasks.py` 的 10 个 helper 调用仍传原中文，见 C5-2。

### 字面量、HTTP 边界与其余检查

- Base 中可直接解析的 63 个字面量 / f-string `HTTPException.detail` 均能在测试里的硬编码期望值找到；比对没有缺项。期望值定义在测试文件，不从 locale 目录生成。GET `/api/task` 六种状态的 Base message 也与测试期望逐字一致。
- `create_app` 注册异常处理器有单独断言；API 错误体、Starlette 404/405、默认 422、任务状态与任务失败回显都经 TestClient HTTP 序列化断言。手工 422 的别名遗漏已由 C5-1 指出。
- locale 各 `error.*` 占位符集合一致；检查 H0 的字面 `ApiError` / `t()` 调用点没有缺少占位符参数。实际对 `t('error.task_id_not_found')` 缺少 `task_id` 的探针抛出 `KeyError('task_id')`，属于 fail-fast，不是静默错文案。
- `error_message` 等失败原因在源码中用于写入、回显或日志；未找到对失败文案做子串匹配并会被本地化破坏的判断。
- `ApiError` 有多处生产消费者；`install_api_error_handlers` 由生产 `create_app` 注册并由测试调用，没有发现其它无第二消费者的新抽象。

## 验证证据

### 当前窄测

命令：

```text
uv run --frozen pytest -q tests/unit/i18n_api tests/unit/test_api_routes.py
```

结果：退出码 0；进度到 100%，无失败。输出含已有 Pydantic deprecation warnings。

### Base scratch 抽查

按卡面通过 `scratch-worktree.sh <repository-path> 341dc874e894408bded13490c73b4e9aea221418 -- ...` 创建 Base 临时 worktree，只复制 `test_error_codes.py` 后运行；pytest 在收集期失败：

```text
ImportError: cannot import name 'ApiError' from 'video_transcript_api.api.context'
ERROR collecting tests/unit/i18n_api/test_error_codes.py
scratch-worktree: removing dirty worktree with 1 change(s): .../worktree
```

该 ImportError 不计作断言红。随后在当前实现中对 `context.t` 做仅进程内错误文案注入，运行对应参数用例；无生产文件修改：

```text
VTAPI_CONFIG=/tmp/vtapi-empty-config.jsonc PYTHONPATH=/tmp:src uv run --frozen pytest -q -p c5_bad_locale_plugin tests/unit/i18n_api/test_error_codes.py -k 'test_static_api_details_match_base_and_have_stable_codes and invalid_url'
```

输出为断言失败（有效红）：

```text
E       AssertionError: assert '__mutated_locale_detail__' == '视频URL不能为空'
FAILED tests/unit/i18n_api/test_error_codes.py::test_static_api_details_match_base_and_have_stable_codes[...-invalid_url]
```

这证明测试的 Base 字面量等值断言会因实际 `ApiError.detail` 漂移而变红；Base 上 ImportError 本身没有被冒充为有效红验。

### 复现探针

手工 422 HTTP 响应：

```text
status= 422
body= {'detail': 'status must be one of: success, failed, all'}
```

任务失败写入与 GET 回显：

```text
written_error_message= 任务队列已满，提交被拒绝
status= 200
body_error= 任务队列已满，提交被拒绝
```

通知回退：

```text
stored_error_message= Failed to submit the task: provider unavailable
notification_error= Failed to submit the task: provider unavailable
sent_marked= 1
```

各探针仅替换 i18n 当前语言为 `en`；任务路由、错误处理器、终态通知实现均使用 H0 生产代码。当前仓库没有 `config/config.jsonc`，故探针未读取部署配置。
