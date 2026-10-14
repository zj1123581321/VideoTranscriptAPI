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