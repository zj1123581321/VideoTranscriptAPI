# 视频号（wechat_channels）接入独立审查

- **审查对象**：`ea71bf3f9167faa732b25928bb959116aac8c4f4..dedd376e6def0ea04b5b9f8ca89168abd4c8e6ad`（H0 冻结，7 commit）
- **risk-tier**：personal（P1 = 数据丢失 / 静默出错 / 崩溃）
- **本轮新证据**：① `urlparse` netloc 矩阵（大小写/端口/userinfo/尾点/IPv6/无 scheme）；② `ocr-review` status=`reviewed`（minimax）；③ H0 `factory.py` 实例生命周期；④ `urlparse` 抛异常面。同一份 diff 复读不算新证据，以上均是生成结论前新跑的。

## 结论

**pass**。无 P1；无阻塞合并的 P2。OCR 5 条均为测试/可维护性意见，本仓判定不升级。

## Findings

无。

## 锁定决策（6 条）

1. **平台字符串 `wechat_channels`**：符合。H0 `git grep` 生产路径的平台标识均为 `wechat_channels`（`url_parser.py:84,293`、`views.py:611`、`history.html:921`）。`shipinhao` 零命中。存量 `config.wechat` / `wechat_webhook` 是企微通知通道，不是视频平台标识。
2. **`X-API-Key` 仅 netloc 相等时携带**：符合。`media_resolver.py:222-229` 用 `urlparse(...).netloc.lower()` 精确相等，且 `_resolver_netloc` 为空则不带头。基类 `base.py:224` 走 `headers=self.download_headers or None`。测试锁 CDN 不带、resolver 流式端点带（`TestConditionalDownloadHeaders`）。
3. **复用 `download_headers` + 403 重下也设头**：符合。首次 `download_file:238` 与 force_refresh 后 `download_file:269` 都调用 `_prepare_download_headers`；重解析语义（反查 → force_refresh → SSRF 校验 → 再下，失败抛 `DownloadFailedError`）相对 base 未改。测试 `test_reresolve_applies_correct_headers_on_retry` 锁重下带 key。
4. **不新增配置项；flag off 落 GenericDownloader**：符合。`config/` 无 diff。`test_downloader_factory.py`：flag on → resolver，flag off + sph URL → `GenericDownloader`。
5. **sph 不进 `SHORT_URL_DOMAINS`**：符合。`url_parser.py:90-95` 仍只有 `b23.tv` / `youtu.be` / `v.douyin.com` / `xhslink.com`；sph 走 `PATTERNS['wechat_channels']`。
6. **静态资产变更递增 `CACHE_NAME`**：符合。base `vta-static-v4` → H0 `vta-static-v5`；`tests/unit/web/test_frontend_auth.py` 断言同步。

## 本轮新角度（4 条）

### 1. netloc 相等判定绕过面

查了，无发现（泄露方向干净；漏带头不是静默成功）。

对 `_prepare_download_headers` 同一谓词跑矩阵：

| 形态 | 结果 |
|---|---|
| 大小写 / 尾斜杠 / `#fragment` | 匹配，该带头 |
| `https://host:8000` vs `http://host:8000`（同 netloc） | 匹配（spec 比的是 netloc 不是 scheme） |
| 无 scheme 的 `host:port` | `_resolver_netloc=""` → 永不带头 |
| 缺省端口 vs 显式 `:80`/`:443`、尾点、userinfo、IPv6 字面量不同写法 | 字符串不等 → 不带头 |
| CDN `cdn.example.com` vs resolver netloc | 从未匹配 |

泄露（不该带却带了）：矩阵无此格；只有 CDN 的 netloc 真等于 resolver 才会带，那就是同一主机。  
漏带（该带没带）：owner 配置畸形或上游 stream URL 与 `base_url` 形态不一致 → 视频号 401/下载失败，不是静默错结果。按 review-discipline，可信配置畸形 ≤P2，且与 spec「netloc 相等」字面一致；要求规范化会反着 spec。接受不修。

### 2. `_prepare_download_headers` try/except pass 与静默出错

查了，无发现（不构成 P1 静默出错）。

`except Exception: pass` 之后恒执行 `self.download_headers = {}`（fail-closed）。`urlparse` 对 str 几乎不抛；会抛的是非 str / 非法 IPv6。下载 URL 已经 `validate_url_safe`。缺 key 的视频号流式端点 → 401 → `DownloadFailedError`，不会「下到文件却没鉴权还当成功」。CDN 路径空头是正确行为。OCR 建议补 debug 日志：可维护性 P3，接受不修。

### 3. 实例级 `download_headers` 串扰

查了，无发现（真实使用方式下不会跨任务共享实例）。

`create_downloader`（`factory.py:46`）每次 `MediaResolverDownloader()` 新实例，无进程级单例。每次 `download_file` 开头重设 headers；403 重下对 `fresh_url` 再设一次。顺序复用同一实例（先视频号后 CDN）会被第二次 `_prepare` 清掉 key。并发意见在 personal 档 ≤P2，且当前工厂不会让两任务共享同一实例。

### 4. 熵增

查了，无熵 +1。新增 `_prepare_download_headers` 有两个调用点（首次 + 重下），不是转发-only、不是无第二消费者。`_resolver_netloc` / `_resolver_api_key` 是 `__init__` 一次缓存，不是第二事实源。无新配置项、无新文件、无单实现接口。

## OCR 前置

- `ocr-review` status=`reviewed`（primary minimax）；verifier 两条腿不可用，5 条均为 `unverified`。
- 工具标注 → 本仓判定（P1 两问：真实使用会触发吗？后果能否接受？）：

| # | 工具 | 本仓 | 两问 | 处置 |
|---|---|---|---|---|
| 1 | except pass 无日志 / low | P3 | 触发：几乎不。后果：空头 + 401，非静默错 | 接受不修 |
| 2 | 测试 `headers == {key}` 过严 / medium | 不成立 | 测试形态，不是生产缺陷 | 不采纳 |
| 3 | 测试写入 `_resolver_netloc` 绕过 `__init__` / high | 不成立 | 生产仍走 `urlparse(base_url)`；测试缺口不导致运行时漏带头 | 不采纳 |
| 4 | 403 测试靠 `HTTPError` 注释不准 / medium | 不成立 | 重下路径另有 `force_refresh` 断言 | 不采纳 |
| 5 | 重下缺「fresh netloc 不同」用例 / medium | P3 测试缺口 | 不触发生产静默错 | 接受不修 |

## Backlog（不占本卡结论）

- `can_handle` 仍用 `domain in url` 子串（与抖音/小红书同一存量模式），非本 diff 引入。
- OCR #1/#5：except 无日志、测试未覆盖「重下换 netloc」；P3，接受不修。
