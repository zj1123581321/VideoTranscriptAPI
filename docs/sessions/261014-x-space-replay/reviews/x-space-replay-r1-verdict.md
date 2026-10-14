# X Space 回放 v2 独立审查 verdict

failure-visibility: p2-only

## 审查对象与结论

- 冻结范围：`9a9e2c5aab6ef2c79f84276fd34eaa5605b44848..1d84cb2c3d2621b9419d245044b22fb1a15a004a`。
- PASS/FAIL/UNKNOWN：**FAIL**（发现 P2/P3）；自动测试 **UNKNOWN**（本轮未运行测试）。
- OCR：**reviewed**，MiniMax 主腿；envelope 的 `coverage=complete`、2 条候选均标为 confirmed。候选已独立核查，未把 OCR severity 当最终定级。
- 整体交付：**不阻断**。personal 风险下没有 finding 同时满足真实使用路径已证实触发、且后果不可接受两问；P1 数量为 0。
- 审查范围：逐项读取冻结 diff 全部 13 个文件；`git diff --check` 无输出。`base.py`、`src/web/` 与 wechat 直连实现未改。

## Findings

### P2-1：Space 正则会从 query 中嵌套的 URL 抢走主 URL 身份

- 违反 spec 1：平台识别应基于 `https://x.com/i/spaces/<13位>` 这一 URL 的 host/path。新增正则见 `src/video_transcript_api/utils/url_parser.py:122`，直接对完整 URL 字符串搜索 `://`，没有限定该 URL 自身的 authority 与 path。
- 复现输入：`https://x.com/user/status/123?t=https://x.com/i/spaces/1AKEmvYqbrOKL`。新增模式会取到 query 中的 Space ID，并把实际推文记作 `twitter_space/1AKEmvYqbrOKL`。API 会把这个 platform/media_id 存作语义去重键，可能与真正的 Space 任务复用同一 view token。
- 影响范围较窄（要求 query 内嵌完整 Space URL），但会把非 Space 资源映射到错误身份；现有 parser 测试只覆盖正向 URL 与长度下限，未覆盖嵌套 URL。

### P2-2：畸形 Content-Length 被静默当成缺失，绕过严格长度比较

- 违反 spec 4：`src/video_transcript_api/downloaders/media_resolver.py:529-536` 在 `Content-Length` 存在但不能转为整数时返回 `None`；`:515` 只在长度非 `None` 时比较写入字节。这样错误头值会关闭严格相等校验，截断响应可能进入后续媒体校验。
- 当前用例只覆盖数字长度不匹配，没有覆盖“头存在但不可解析”。该问题依赖解析服务或代理发出畸形头，按 personal 风险列为 P2。

### P2-3：1800 秒预算耗尽后仍会再发一次 GET

- 违反 spec 5：`src/video_transcript_api/downloaders/media_resolver.py:420-447` 每轮先 GET，再检查剩余预算。若前一轮 sleep 已耗尽 deadline，循环仍会进入下一轮 GET；单次请求 timeout 为 60 秒，因此等待可超过 1800 秒，或在超限后才收到 200。
- 等待预算测试只累计 sleep 时间，没有计入 deadline 后这次请求耗时。触发条件是回放恰好未在 1800 秒内就绪；超额上界由 GET timeout 限制。

### P2-4：同源请求遇跨主机重定向时可能转发 X-API-Key

- 违反 spec 10：`src/video_transcript_api/downloaders/media_resolver.py:417-422` 对与配置 netloc 相同的 URL 设置 `X-API-Key`，但 `requests.get` 默认跟随重定向。Requests 重建跨主机请求时会剥离 `Authorization`，不会剥离自定义 `X-API-Key`；若 stream URL 返回跨主机 30x，密钥会随重定向请求发送到另一 netloc。
- 当前契约路径预期直接返回 202/200，未证明该端点会重定向，因此列为 P2；现有测试覆盖初始目标 netloc，没有覆盖重定向后的实际请求头。

### P3-1：非字符串错误 message 可在 Space 分类前触发 AttributeError

- 无直接对应的卡面 spec，按审查规则降级。`src/video_transcript_api/downloaders/media_resolver_client.py:317-320,335-345` 接受 dict 形状的 `error`，但把其中任意 truthy `message` 传给 `.lower()`；若 `message=123` 且带已知 `code`，新增 Space 检查会在原有 code 分类前崩溃。正常 resolver 契约要求字符串，此 finding 只针对畸形响应，P3、不阻断。

## 不变式核对

| Spec | 判定 | 证据摘要 |
|---|---|---|
| 1 URL 识别 | FAIL | P2-1：query 内嵌 URL 可改变主 URL 的 platform/media_id。 |
| 2 202 轮询 | PASS | Space 路径走专用轮询，同 URL 重 GET；202 响应未传入基类写盘。 |
| 3 stream 路径与 netloc | PASS | 由 `path` 匹配 Space stream；不同 netloc 也进入专用分支。 |
| 4 Content-Length | FAIL | P2-2：存在但不可解析的长度值被当作缺失。 |
| 5 等待上限 | FAIL | P2-3：deadline 后仍启动一次 GET。 |
| 6 终态提示 | PASS | live/unstarted 与 replay disabled/expired 映射为两类可见提示。 |
| 7 m4a 后缀 | PASS | `twitter_space` 或 `media_type=audio` 选择 m4a。 |
| 8/9 禁改边界 | PASS | 冻结 diff 未改 base.py、`src/web/` 或 wechat 直连实现。 |
| 10 API key 主机范围 | FAIL | P2-4：自动跨主机重定向不剥离自定义 key header。 |

## 验证记录

- `git diff --numstat 9a9e2c5aab6ef2c79f84276fd34eaa5605b44848..1d84cb2c3d2621b9419d245044b22fb1a15a004a`：13 个文件，978 insertions、8 deletions。
- `git diff --check 9a9e2c5aab6ef2c79f84276fd34eaa5605b44848..1d84cb2c3d2621b9419d245044b22fb1a15a004a`：无输出。
- 测试套件未运行；本卡是只新增 verdict 的独立审查。
