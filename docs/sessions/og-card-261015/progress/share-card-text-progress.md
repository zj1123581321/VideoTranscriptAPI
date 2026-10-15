# share-card-text 进度存档（dlg-20261015-161137-54d4e3）

## 段 1：设计文档入库 + 现场核查完成

- **当前阶段**：implementing（卡 A：总结成功后生成分享卡片文案）
- **本段结论**：design.md / research.md 已原样复制入仓（md5 校验一致）。现场核查完成：挂点选定 coordinator（总结 GENERATED 之后生成数据）+ llm_ops._save_llm_results（summary 落盘同层做删旧/写新）；落盘走 llm_ops 内 tmp+os.replace 原子写，不改 cache_manager.py（Scope-Globs 不含它）。
- **关键决策与已否决方案**：
  - 已否决「coordinator 内直接落盘」：coordinator 不知道任务缓存目录（无 platform/media_id），需扩接口，改动面更大。
  - 已否决「给 cache_manager.save_llm_result 加 share_card 类型」：cache_manager.py 不在本卡 Scope-Globs 内。
  - 选定与 chapters 层同构的模式：processor 生成 → coordinator 返回值携带 → llm_ops 按 GENERATED 落盘；失败隔离双层（processor 内 catch + coordinator 调用点 catch），error 日志在 llm_ops 层记（那里才有 task_id）。
- **下一步唯一动作**：写 share_card prompt/schema + ShareCardProcessor + processor 单测。

## 段 2：端到端链路完成（processor → coordinator → llm_ops 落盘）

- **当前阶段**：implementing（代码全部落地，验收测试全绿）
- **本段结论**：ShareCardProcessor（契约校验/失败隔离/summary 模型复用）、coordinator 挂点（总结 GENERATED 后、失败原因随返回值带回）、llm_ops 落盘块（tmp+os.replace 原子写；resummarize 先删旧卡再写新；calibrate_only 与未请求总结的轮次不动文件）均完成。share_card 全部 32 条测试绿；make test 仅剩 1 个失败 test_unix_domain_socket_is_not_blocked，经基线 552f496e worktree 复跑确认为继承红（AF_UNIX path too long，worktree 路径过长，环境性问题）。
- **关键决策与已否决方案**：
  - 否决「share card 块无条件 get_cache」：踩掉 test_llm_ops_helpers 两条「全流程默认不探缓存」的性能约定测试；改为「result_dict 带 share_card 键（走过 coordinator 的生产路径）才触碰磁盘」，旧式手工 dict 不动卡片也不探缓存，并新增测试锁死该约定。
  - 长度校验用权重法（CJK 字符计 1、其余计 0.5）：「≤30 汉字（英文 ≤60 字符）」的契约表述在混合文本下无歧义，60 个英文字符恰好用尽额度。
  - 截断职责收敛在 build_share_card_user_prompt 一处（processor 不预切片，避免双处截断丢失 truncation 标记，曾踩坑一次）。
  - FAILED 轮次也删旧卡（即使磁盘旧总结未被覆盖）：按卡面锁定决策「重新总结时先删」字面执行，避免失败后遗留过期卡片；页面表现退化为设计不变式 1（无卡 → 无 og:image）。
- **下一步唯一动作**：红验（改坏 llm_ops 写入点确认转红）后提交收尾、推送、开 draft PR。
