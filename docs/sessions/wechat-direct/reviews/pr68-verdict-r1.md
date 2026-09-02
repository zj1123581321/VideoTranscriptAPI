# PR #68 独立审查 verdict（R1）

- **审查对象**：`git diff 4e0a5ab0e8841b07577a2d9e984a078f18a6f68c..b2d67c3`（H0 冻结；之后的新提交不属于本轮）
- **风险等级**：internal（P1 红线：数据丢失、静默出错、崩溃、越权访问、损坏他人数据）
- **真实使用方式**：单机单用户部署，resolver 为自有服务，视频号 URL 来自用户提交
- **Verdict 文件**：`docs/sessions/wechat-direct/reviews/pr68-verdict-r1.md`（本文件）
- **审查人**：Kimi（独立 review 卡 dlg-20260902-122616-64c9fb，全新会话，未见实现方报告）

## 本轮新证据

1. 在 b2d67c3 临时 worktree 实跑三个受影响测试文件：`test_media_resolver_wechat_direct.py` + `test_media_resolver_client.py` + `test_media_resolver_downloader.py`，**64 passed**。
2. 降层实测探针：按 `test_final_size_mismatch_raises` 的场景（content_length = head+50、CDN 恒 410）实跑 `_download_wechat_direct`，实际抛出的是 `wechat direct no progress`（零进展分支），**不是**测试名声称的 size-mismatch 分支（见 P2-2）。
3. OCR 前置扫描：`ocr-review --from 4e0a5ab --to b2d67c3`，status=**reviewed**（primary_selected，非 skipped），13 条 finding 逐条分诊见下表。

## 不变式逐条核验

| # | 不变式 | 结论 | 证据 |
|---|--------|------|------|
| 1 | token 保密 | ✅ | 全部日志/异常只含 sph_code/offset/字节数/status（`media_resolver.py:343-470`、`media_resolver_client.py:209-264`）；cdn_url 仅存在局部变量 `payload`，不入 `_resolve_cache`、不落盘；连接失败只记 `type(e).__name__`；测试 `test_returns_flat_json_and_omits_cdn_from_logs` 与 `_no_secret` 断言锁死 |
| 2 | 密钥隔离 | ✅ | CDN 请求头只有 `Range`（`media_resolver.py:445-448`），X-API-Key 仅由 client 发向 `self.base_url` 拼出的 `/direct`（`media_resolver_client.py:214-215`）；测试断言 `X-API-Key not in CDN headers` 且 /direct 携带该头 |
| 3 | 完整性 | ✅ 实现 / ⚠️ 防线 | ftyp bytes[4:8] 校验（`media_resolver.py:318-322`）；Content-Range 起点 != offset 即换链（`:449-456`）；收尾 `os.path.getsize(local_path) == content_length` 断言打在终态文件本身（`:373-378`）。但收尾校验无有效测试锁死（P2-2） |
| 4 | 有界失败 | ✅ | 换链上限 5（`:418-422`）；连续零进展 2 次放弃（`:414-417`）；超限/畸形/no-ftyp 全部 fail fast 抛错；溢出 chunk 不写入、不截断凑数（`:462-468`）；任何异常 `_discard_temp` 销毁临时文件（`:379-381`） |
| 5 | 路由隔离 | ✅ | `_wechat_stream_sph_code`（`:296-307`）：netloc 小写精确相等 + path 正则 `^/api/stream/wechat_channels/([A-Za-z0-9]{1,64})$`；其他 URL 走既有 `_prepare_download_headers` + 基类逻辑；`test_non_wechat_url_does_not_call_direct` 锁死 |
| 6 | SSRF | ⚠️ 一处缺口 | 每次 CDN GET 前过 `validate_url_safe`（`:393-398`），但 requests 默认跟随 30x 重定向，**redirect 目标未过校验**（P2-1） |

## Findings

### P2-1 CDN 请求跟随重定向，redirect 目标绕过 validate_url_safe（违反不变式 6）

- **证据**：`media_resolver.py:445` `requests.get(cdn_url, headers={"Range": ...}, stream=True, timeout=...)` 未传 `allow_redirects=False`，requests 对 GET 默认跟随最多 30 次重定向；`validate_url_safe` 只在 `:394` 校验初始 cdn_url，30x 的 Location 目标（可为内网地址）不再过 SSRF 校验。
- **两问**：①会被触发吗——cdn_url 来自自有 resolver、指向 finder.video.qq.com，微信 CDN 正常直接回 206/4xx，30x 到内网需 CDN 行为异常或中间设备介入，概率低（无真实 token 无法实测线上 CDN 是否 30x）；②后果——请求不携带任何凭据（无 X-API-Key、无 cookie），响应体写入本地临时文件、不回显不记日志，最坏是内网内容拼进 mp4 导致文件损坏/下载失败，无数据外泄通道。后果可接受但有明确防线缺口 → **P2**，不阻塞合并。
- **建议**：CDN GET 加 `allow_redirects=False`（30x 即 status != 206，自动落入既有换链逻辑，与有界失败协议天然兼容）。

### P2-2 `test_final_size_mismatch_raises` 名不符实：收尾 size 校验无测试锁死（不变式 3 的防线缺口）

- **证据**：`tests/unit/test_media_resolver_wechat_direct.py` 中该测试用 8 份相同 payload + 恒 410 的 getter。实测（本审查探针，输出见上）：第二次零进展即在 `media_resolver.py:414-417` 抛 `wechat direct no progress`，**永远到不了** `:373-378` 的 `getsize != content_length` 分支。全 diff 无其他测试覆盖收尾 size 校验。
- **两问**：①实现本身正确（探针与代码阅读双重确认），缺的是回归防护——收尾断言是「产出正确文件」的最后一道防线，改坏它没有任何测试变红；②后果是未来的回归静默通过 → **P2**，建议补一条真正打到 size-mismatch 分支的测试（如 CDN 返回短 body 后以 206 正常结束流），并给现有测试改名或加错误消息断言锁定目标分支。
- 不阻塞合并（实现无缺陷），但必须记 backlog。

### P3（记 backlog，不阻塞）

1. **换链后未复核新 payload 的 content_length/encrypted_head_bytes 与首次一致**（不变式 3 边缘）：`_append_wechat_cdn` 换链后只取 `cdn_url`（`media_resolver.py:423-433`），若 resolver 对同一 sph_code 返回变化的总长，最终校验仍按首次 content_length，理论上可产出「长度正确、内容混合」的文件。真实使用下同一 sph_code 内容在下载窗口内变化的可能性极低（自有 resolver）。
2. **两处不可达死代码**：`_append_wechat_cdn` 循环末尾的 `raise DownloadFailedError("incomplete")`（`media_resolver.py:434-437`，循环内 ==/> 两种出口已覆盖）；`fetch_wechat_direct` for 循环后的 `raise NetworkError`（`media_resolver_client.py:262-264`，`max_retries = max(1, ...)` 保证循环内必 return/raise）。
3. **SSLError 被当瞬时断流处理**（OCR [8]，工具标 medium）：`_stream_wechat_cdn_range` 的 `except requests.RequestException` 涵盖 SSLError，证书校验失败会走换链而非 fail fast。两问：换链有上界（5 次后抛错），不静默产坏文件、不泄密；单机直连部署无透明代理 → P3。建议单独 catch SSLError 直接抛 DownloadFailedError。
4. **SSRF 校验失败重抛缺 `from e`**（OCR [12]）：`media_resolver.py:396-398` 丢原始异常链，诊断性小事。
5. **测试加固类**（OCR [0][1][3][4][5]）：secret 断言用子串且排在严格相等断言之后（相等先失败会跳过泄露断言）；`patch_get`/`patch_get` 饱和重放最后一条响应；缺 `encrypted_head_bytes=0`、非法 base64 边界用例。均为测试健壮性，不影响生产行为。

### 驳回的 OCR finding

- **OCR [10]**（head-only 分支 `encrypted_head_bytes > content_length`「静默成功」）：误读。该分支写入 head 后 `len(head) != content_length` 必抛 `DownloadFailedError` 且临时文件被销毁（`media_resolver.py:364-369, 379-381`），不存在静默成功。不成立。
- **OCR [11]**（validate_url_safe 应提升到换链边界而非每次请求）：与 spec 不变式 6 明文「每次 CDN 请求前过 validate_url_safe」直接冲突，且循环每轮恰好一次 GET，当前粒度即 spec 要求。反着 spec，不成立。

## 降层三问

**① 最终文件返回给转录流程之前，哪些已发生的动作不可逆？**
没有不可逆动作。写入目标是 `temp_manager.create_temp_file` 的独立临时文件，任何异常经 `except Exception: _discard_temp(local_path); raise`（`media_resolver.py:379-381`）销毁；网络侧全是 GET/Range 只读请求，不改 resolver、不改 CDN 状态。唯一的「交付」是 return 路径那一刻，此前全部可回滚。

**② 换链续传的 offset 单一事实源是什么、并发场景下唯一吗？**
单一事实源是 `_append_wechat_cdn` 的栈帧局部变量 `offset`：初值 `len(head)`（client 已校验 `len(head) == encrypted_head_bytes`），只由 `_stream_wechat_cdn_range` 返回的**实际写入字节数** gained 累加（`media_resolver.py:402-403`），不从 Content-Range、不从 resolver 响应反推。并发：每次 `download_file` 调用持有独立临时文件与独立栈帧 offset，downloader 实例上没有跨调用的下载进度状态（`_resolve_cache`/`_video_url_to_page` 与本路径无关）；单机转录流程串行调用。唯一且安全。

**③ 保护覆盖的是「写入字节数」还是「产出正确文件」这一行为？**
覆盖到终态交付物本身：收尾断言是 `os.path.getsize(local_path) == content_length`（对落盘文件的实测，不是中间计数器）+ head 的 ftyp magic 校验，量纲与「产出正确文件」一致。不在覆盖范围内的是「内容字节正确性」（CDN 返回同长度错误内容不可发现）——spec 只要求字节数 + ftyp，保护与 spec 一致。唯一缺口是这道终态断言没有回归测试锁死（P2-2）。

## 总结论

**pass**。无 P1；必修清单为空。六条领域不变式实现层面全部成立（实测 64 项单测全绿 + 降层探针佐证）。两条 P2（redirect 过 SSRF、收尾校验缺测试）与五条 P3 记 backlog，不阻塞合并，建议下一轮或后续卡处理。
