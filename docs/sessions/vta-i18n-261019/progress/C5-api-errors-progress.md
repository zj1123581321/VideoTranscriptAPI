# C5 API errors progress

### 里程碑 1：JSON API 错误响应本地化
- 当前阶段：implementing
- 本段结论：新增稳定 `error_code` 和本地化字符串 `detail` 的响应处理；覆盖任务、审计、上传、用户配置与令牌校验错误，并保持默认中文文案逐字一致。新增测试锁定静态/动态错误文本、英文无 CJK、真实鉴权与空 URL 响应，以及 FastAPI 422 原形状。
- 关键决策与已否决方案：由 `ApiError` 按错误文案映射稳定代码，集中异常处理器序列化；不改 HTML 路由、前端或 422 请求体。
- 下一步唯一动作：完成 task_status 失败原因写入路径盘点；因 `llm_ops.py` 超出当前 Scope-Globs，已提交 seq 1 scope-request，获准后仅补该文件的失败原因本地化。
