# X Space 回放走 MediaResolver v2 文件协议 — 进度存档

追加式：每个里程碑一段，与该里程碑的 commit 同一次提交；不回头改写历史段落。

---

## 里程碑 1：URL 识别与跨服务契约样本入库

- **当前阶段**：implementing（第 1/3 步：URL 解析 + fixture）
- **本段结论**：`URLParser.PATTERNS` 新增 `twitter_space`，排在 `twitter` 之前，
  `https://x.com/i/spaces/<13位字母数字>`（含 twitter.com 子域、`/peek`、尾斜杠、`?s=20`）
  的 `parse()` 与 `extract_platform()` 均给出 `platform=twitter_space` + 裸 id；
  `/i/spaces/short` 这类长度不符的不再冒充 Space。推文 `/status/<数字>` 仍为 `twitter`（71 passed）。
  四份 fixture 按 MediaResolverAPI PR #45（分支 `card/x-space-mat`，commit b5f462a）
  的真实响应构造：`stream_202.json` = `_202_extracting()` 的 `{"status": "extracting", "retry_after": 5}`；
  `resolve_success.json` = `_build_response()` 对 `TwitterSpaceService._parse_response()`
  产出的 VideoInfo 的序列化（`media_type=audio` / `duration=null` / `variants=null` /
  `video_url=/api/stream/twitter_space/<id>`）；两个失败样本 = `resolve_url()` 捕获
  `VideoResolverError` 后返回的 HTTP 200 `success=false` + 字符串 `error`
  （终态链：`SpaceNotReplayError` → `VideoResolverError`；全源失败链：`VideoNotFoundError`
  → `VideoResolverError`）。
- **关键决策与已否决方案**：
  - 对方 `_SPACE_ID_PATTERN = ^[0-9A-Za-z]{13}$`，故 URL 正则锁 13 位并加 `(?![A-Za-z0-9])`
    防止把 14 位串截成 13 位——**否决**「宽松 `\w+` 交给下游报错」，
    那会让非法 id 以合法形态进入 resolve。
  - resolve 失败体是**字符串** `error`（`ResolveResponse.error: Optional[str]`），
    不是 `{code, message}` 对象；本仓 `_classify_failure` 已有 `isinstance(error, str)` 兼容分支，
    **否决**为此新建 `{code,message}` fixture（与对方实现不符）。
  - **否决**为 Space 单独抽一个 provider/client 类：v2 契约只多出「202 轮询 + m4a 后缀」两件事，
    都在既有 `MediaResolverDownloader` / `MediaResolverClient` 内可闭合。
- **下一步唯一动作**：给 `MediaResolverClient._classify_failure` 加 Space 分支
  （`is_live`/`is_upcoming`/未开播 → `这场还不能回放`；`replay is disabled`/过期 → `回放不可用`），
  用四份 fixture 驱动写红测。
---

## 里程碑 2：Space v2 客户端（202 轮询 → 完整 m4a）

- **当前阶段**：implementing（第 2/3 步：下载器 + 错误映射）
- **本段结论**：`MediaResolverDownloader.download_file` 在视频号分支之后加 Space 分支：
  命中 `<resolver>/api/stream/twitter_space/<13位id>` 时同步轮询同一 URL——202 按响应
  `retry_after` 退避、502/503 在预算内退避重试、400/404 转终态文案、200 直接落盘且
  **字节数与 Content-Length 严格相等**（不走基类 1024 容差），等待上限 1800 秒，
  超时抛含「回放仍在准备」的 `DownloadFailedError`。`_infer_file_ext` 增加
  `platform=twitter_space` / `media_type=audio` → `m4a`。`MediaResolverClient._classify_failure`
  在既有分类之前加 Space 分支，直播/未开播 → 「这场还不能回放」，禁用回放/过期 →
  「回放不可用」。四个定向文件 242 passed。
- **关键决策与已否决方案**：
  - **否决**「等 20 分钟/1800 秒是就绪保证」：写死为上限，超时必给用户可见错误，
    文档明写「服务端后台物化，客户端不保证在上限内就绪」。
  - **否决**用 `force_refresh` 重解析当 502 的补救：对方 v2 的补救语义就是「下次 GET
    同一 URL 重新 spawn」，重解析改不了服务端物化状态；测试锁死「502 期间零次 resolve」。
  - **否决**把 400/404 复用成 `InvalidURLError`（既有「无法识别的链接」文案）：那正是卡面
    点名要避免的用户可见错误；改用 `NonVideoContentError` + Space 专属文案。
  - **对轴表的一处扩写（显式提出）**：卡面只列了 error 含 `is_live` → 「这场还不能回放」，
    但对方 `YtdlpProvider` 对未开播/缺失回的是 `live_status=is_upcoming` / `live_status=missing`
    （`live_status not in ("was_live","post_live")` 即终态）。只认 `is_live` 会让「未开播」
    掉进默认分支显示「解析失败，稍后再试」。故关键词扩为
    `is_live` / `is_upcoming` / `live_status=missing` / `is not a replay`，并加测试锁死四格。
  - 单测不真睡：monkeypatch `media_resolver.time.sleep` + `time.monotonic`，
    假时钟只在被 sleep 时推进，1800 秒预算跑完约 0.1 秒。
- **下一步唯一动作**：补 `docs/guides/media_resolver.md` 的 Space 客户端协议节
  （202 轮询 / m4a / 1800 秒上限 / 占一个转录 worker / 不接直播与 t.co），跑 `make test`。

---

## 里程碑 3：收尾（文档、全量测试、红验、push）

- **当前阶段**：done（本卡可交付，等主脑验收）
- **本段结论**：`docs/guides/media_resolver.md` 增补「X Space 回放（两阶段文件交付）」节
  （202 轮询 / 200 Content-Type audio\/mp4 / 400·404 / 502 / 503 / m4a / 1800 秒上限 /
  占用一个转录 worker / 不接直播与 t.co），错误对照表与故障排查表各补 3 行。
  全量 `pytest tests` = 3961 passed, 3 skipped, 1 subtests passed in 177.33s（exit=0）。
  五处红验全部按最小注入转红（等待预算、1024 容差、超时文案、m4a 分支、502 重试），
  外加第六处（临时文件清理）确认截断测试判据非恒真。已 push 到
  `origin/card/vta-261014-x-space-replay`（远端 b8232ed1）。
- **关键决策与已否决方案**：
  - **否决**把 `verify-output.log` 用 `git add -f` 硬塞进仓：`.gitignore:30` 收 `*.log`，
    绕过忽略闸属「扫描式守卫变红只许上报」那类；改为把归档件放在 delegate report 目录
    （`verify-output.log` / `make-test-final.log`），仓内只留 commit 与报告引用。
  - **否决**在 `tests/unit/test_asr_monitor_alert_delivery.py` 上「顺手修」那条
    `OSError: AF_UNIX path too long`：它是执行器沙箱 `TMPDIR` 长达 129 字符导致的继承红
    （同一条测试 `TMPDIR=/tmp` 下 14 passed），与本卡无关且不在允许清单内。
  - 合并「等待预算」两格测试为一格（超时文案 + 轮数有界 + 累计 sleep ≤1800），
    判据不丢、净减 6 行，用于把 diff 从 838 行压回 832 行。
- **下一步唯一动作**：主脑验收；合并前复核对方 MediaResolverAPI PR #45 的
  `_202_extracting()` 与 `space_cache._record_failure()` 未再改动。
