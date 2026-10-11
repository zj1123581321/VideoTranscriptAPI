# 通知修复轮（r1/r2）分支处置记录

261007-notify-slim 修复轮产出两个远程分支，分支删除前在此归档处置结论，
删除后不丢任何决策上下文。

## r1：origin/card/VideoTranscriptAPI-261007-notify-r1（顶提交 1f25f4ea）

**分支做的事**：成功终态缺持久化 result 时，`_render_success_body` 由 raise
改为打 `COMPLETION-BODY-MISSING` 警告并按 `completion_body=None` 渲染
（仅抬头 + 查看链接），照常发送并标记已发送，不再每轮补发渲染失败无限重试；
补发路径对成功行不再拼接 completed_at 错误注记（避免渠道侧把成功消息标成
失败表情）；channel.py 注明超长正文分段由 wecom_notifier 库负责。

**main 现状：已被等价实现覆盖并演进**（`src/video_transcript_api/api/services/terminal_status.py`）：

- `_render_success_body`（约 267 行起）保留 `COMPLETION-BODY-MISSING` 警告与
  「missing result 确定性缺失、不为 body 重试；其他渲染异常仍传播并保持待发」
  语义；降级产物从「`completion_body=None` 纯抬头+链接」演进为显式降级文案
  「⚠️ 总结未能载入，请在网页查看」+ 查看链接，空 dict 也纳入 missing（N2）。
- `_compose_dispatcher_error` 成功行返回 `None` 原样保留（约 469-470 行）。
- 行为由 `tests/unit/test_terminal_notification_outbox.py` 的
  `COMPLETION-BODY-MISSING` 断言（缺 result、非 dict result、空 dict result
  等用例）锁定。

## r2：origin/card/VideoTranscriptAPI-261007-notify-r2（顶提交 9f68fe7f，叠在 r1 之上）

**分支做的事**：飞书 interactive 卡片超预算时在本层手写分段——新增
`FEISHU_CARD_MAX_BYTES = 18000` 与 `_split_feishu_card_content`（按空行段落
贪心打包，单段超限按 UTF-8 字符边界硬切），`send_rich` 拆成多张卡片发送，
第 2 张起标题加 "(i/n)" 后缀。

**main 现状：该路线已被显式否决**。`src/video_transcript_api/utils/notifications/channel.py`
约 234-235 行注明：「本层不截断 completion_body；分段由 wecom-notifier 库负责；
飞书 interactive 卡片暂不分段，企业微信超长单行有边界缺陷，见
zlxlabs/wecom-notifier#2 #3、本仓 #195」。r2 的手写分段方案不再复活；
飞书分段若未来要做，应在 wecom-notifier 库侧实现。

## 结论

r1 的三个意图点均已在 main 有等价实现（部分演进增强）并有测试锁定；
r2 所代表的分段路线已被 main 注释显式否决。两分支可安全删除。
