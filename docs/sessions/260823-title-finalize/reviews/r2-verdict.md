# r2-verdict：title-finalize 反向审查（persist 路径穷举）

- **审查范围**：`5ce323aad3fbaa3525df959f74a2d873d84d85b5..f1ee994b8db722bc5862e775b7a0ac9fc8ca80ce`（PR #62，冻结范围，不含此后 verdict 提交）
- **审查者**：Kimi 执行器（独立 review 卡 r2，反向视角）
- **日期**：2026-08-23
- **risk-tier**：personal；P1 仅当「真实使用方式下会把错误标题持久化进 video_cache 且不报错」
- **本轮唯一问题**：还有没有路径能把 URL basename / `Unknown` **静默写进 video_cache**？

## Verdict

**pass** — 反向穷举未发现本 diff 引入或遗留未守的 video_cache 静默写占位符路径。唯一剩余路径（F1，merge_metadata 默认值预填使补拉失效）为存量行为、base/head 完全一致，记 P2 backlog。

## 本轮新证据（与 r1 不同的检查）

r1 正向确认「6 处 save_cache 前有 finalize」；本轮反向穷举「谁能写 video_cache」：

1. **video_cache 写入点全仓枚举（head f1ee994）**：`git grep INSERT/REPLACE INTO video_cache` 全仓仅 `cache/cache_manager.py:735`（`save_cache` 内）一处 SQL 写入；`save_cache` 全仓调用点仅 `transcription.py` 6 处。`llm/core/cache_manager.py` 的 `video_cache` 只是产物目录名，不写表。
2. **save_cache 有/无 finalize 全量表**（head 行号，逐一核对上下文）：

   | # | save_cache 行 | 场景 | finalize 行 | 紧邻 |
   |---|---|---|---|---|
   | 1 | 1838 | YouTube API 快路径·平台字幕直用 | 1836 | ✅ |
   | 2 | 1933 | YouTube API 快路径·FunASR | 1932 | ✅ |
   | 3 | 1966 | YouTube API 快路径·CapsWriter | 1965 | ✅ |
   | 4 | 2141 | 平台字幕路径（get_subtitle_result） | 2139 | ✅ |
   | 5 | 2321 | 常规下载·FunASR | 2319 | ✅ |
   | 6 | 2369 | 常规下载·CapsWriter | 2368 | ✅ |

   YouTube API 快路径（卡面点名方向）3 处 save_cache **不漏点**；独立 `download_url` 路径汇入常规下载流（站点 5/6），同样过 finalize，且 finalize 的 `url=parse_url`（平台页 URL，非 CDN 下载直链），basename 兜底取值正确。
3. **`_fail_task_and_notify` 是否写 cache**（head 行 857–944）：只调 `cache_manager.update_task_status(task_id, FAILED, download_url=..., error_message=...)`，**不传 title/author**；且 `update_task_status` 写的是 `task_status` 表（cache_manager.py:2431 `UPDATE task_status`），不是 video_cache。失败收口无 video_cache 写入。✅
4. **`merge_metadata` 反向核实（新发现 F1 的证据）**：head 行 303–306，该函数（本 diff 未改）在 `parsed_metadata` 为真但 title/author 为空时，就地填入 `extract_filename_from_url(url) or "Untitled"` 与 `"Unknown"`。再核对 downloader 实现：`xiaoyuzhou.py:224`、`generic.py:767` 均为 `title=info.get("video_title", "")`——**get_metadata 成功但返回空标题是现实可达的**（r1 F3 亦承认 GenericDownloader 对小宇宙 URL「大概率仍得空标题」）。
5. **task_status 表的 title 写入**（旁证，非 video_cache）：`llm_ops.py:468/818`、`transcription.py:1371` 等 `update_task_status(..., title=...)` 写 task_status 表，且 `cache_manager.py:2369` `if title:` 空串跳过；不在本卡 P1 定义（video_cache）范围内。

## 降层三问（短答）

1. **终态写入前有哪些不可逆动作？** 音频落盘、转录文本生成、中途通知；video_cache 的唯一写边界是 `save_cache`（唯一 SQL 入口），6/6 站点 finalize 紧邻其前。
2. **守卫用的值在部署形态下唯一吗？** finalize 产出 `(title, author)` 依赖同进程 downloader 实例内存缓存；personal 单实例部署，无副本竞争，成立。
3. **保护覆盖写入还是行为？** 写入侧全覆盖（唯一 SQL 入口 + 6/6 调用点）；行为层（中途通知、handoff 字段顺序）r1 已记 P2 并接受，本轮不重开。

## Findings

### F1 — `merge_metadata` 默认值预填使 finalize 补拉失效（本轮新发现）

| 维度 | 内容 |
|------|------|
| 工具标注 | —（本仓反向穷举发现，非外部工具） |
| 本仓判定 | **P2（backlog）** |
| 触发路径 | `get_metadata` **成功但返回空 title/author**（如 generic 页无 og:title、xiaoyuzhou 解析出空串不抛异常）→ `merge_metadata`（head:303–306，存量未改）就地填入 basename/`"Unknown"` → `finalize_presentation_metadata` 的 `needs_retry` 为 False（title/author 均非空）→ 补拉不发生 → basename/`Unknown` 静默写进 video_cache |
| P1 两问 | ① 真实使用下会触发吗？**可达**（上述 downloader 实现允许成功返空标题）；② 后果能否接受？错误标题静默持久化——孤立看命中卡面 P1 定义，**但**该路径 base 与 head 行为逐字节一致，非本 diff 引入或加剧；按 review-discipline「只审本次 diff；存量代码问题直接记 backlog」降为 P2 |
| 溯源 | I1 的覆盖边界：I1 只管「get_metadata 异常」分支，不管「成功返空」分支 |
| 处置 | backlog：后续把 `merge_metadata` 步骤 2 的默认值填充删除或推迟到写边界 finalize（届时 finalize 的 needs_retry 才能对成功返空路径生效）。本 PR 不阻塞 |

### r1 已登记项（不重开）

r1 的 F1（宽 except）、F2（handoff_payload 顺序）、F3（GenericDownloader 优先补拉）、F4（全命中不 finalize）均已判 P2/P3 接受不修，本轮核实结论不变，不换措辞重提。

## 结论摘要

反向问题的答案：**除存量 F1 外，没有路径能把 URL basename / `Unknown` 静默写进 video_cache**。video_cache 有唯一 SQL 写入口，6 个调用点全部 finalize 紧邻；`_fail_task_and_notify`、YouTube API 快路径、平台字幕路径、独立 download_url 路径均无漏点。verdict：**pass**。
