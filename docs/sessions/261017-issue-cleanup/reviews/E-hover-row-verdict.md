# 撤权 hover debounce 跨行行为审查结论

审查范围：`c29326f09df1f7f7b1d8dcfdd3df53f14b6d620f..5fd502e76ee171cb20753017b1e34e70e7dfd08c`。

## Verdict

failure-visibility: clean

修复在成功撤权后保留其他行已排队的 hover 摘要请求，并在回调执行时核对该行仍持有原分享 token。没有发现生产逻辑回归、额外状态、请求 abort 或 fallback。最初提出的 P2 测试缺口已撤回：该意见漏看已有 full-chain 撤权用例，新增回归检查现已覆盖 A 行撤权后的延迟摘要请求。

OCR 结论为 `reviewed_fallback`。存量 detached row 若仍保留 `data-vt` 的情况是已接受的低级 P2，本次不扩展处理范围；in-flight 请求也不 abort。

## 不变式轴与检测点

| 状态 / 行为 | 检测点 |
|---|---|
| A 行撤权成功后，其待执行 hover timer 不得再发起摘要请求 | [full-chain E2E](../../../../e2e/tests/local-upload-full-chain.spec.ts)：暂停时钟、点击 A 的撤权按钮、确认 DELETE 200、推进 301 ms，断言 A 的摘要 GET 数为 0。移除回调 token guard 的红验得到 Expected 0 / Received 1。 |
| A 行撤权期间，B 行仍持有 token 时，B 的 timer 必须保留并成功读取摘要 | [local-upload E2E](../../../../e2e/tests/local-upload.spec.ts)：阻塞 A 的 DELETE，hover B，再放行 A；推进 301 ms，断言 A 请求数为 0、B 为 1、B 响应 200 且 tooltip 可见。旧实现红验为 B Expected 1 / Received 0。 |
| 撤权后的读取仍拒绝访问，且撤权确实写入数据库 | [生命周期集成测试](../../../../tests/integration/test_local_upload_lifecycle.py) 保留 summary 404 断言；跨行 E2E 从数据库回读 `share_active=false`。 |
| 浏览器错误检查继续生效 | full-chain 用例保留原有 console/network 错误断言。 |
| 已发出的请求与 detached row 边界 | 本次不增加 abort 或 detached-row 行为；detached row 的接受说明见上。 |

独立审查者未执行 Chromium。上表中的红绿浏览器证据来自实现代理本地实跑：full-chain 和跨行用例修复后均通过；对应两次红验分别得到 A 的摘要 GET 为 1，以及 B 的摘要 GET 从预期 1 变为实际 0。既有生命周期测试针对撤权 404 的结果也已通过。
