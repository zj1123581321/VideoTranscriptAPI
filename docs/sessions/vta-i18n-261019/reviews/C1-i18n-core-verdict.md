# C1 i18n 核心实现审查

failure-visibility: clean

## 结论

审查区间 `c2fa382e18734a0da410fdec1912da4c7b6c26d2..2d1a64866cc9875c0363cbe5daded5bb5e2a6bd3` 符合本卡指定的设计要点 1、2 与关键不变式 1–3。未发现 P1/P2 或阻断交付的问题。另有一条不阻断的 P3 结构候选，详见下方。

## 契约核对

1. **语言配置**：`logger.py:84-90` 只在解析结果为对象且显式含 `language` 时校验；非法值由 `validate_language()` 抛错并列出 `zh-CN, en`（`i18n/__init__.py:47-61`）。缺省不写入配置字典，`get_language()` 读取时按 `zh-CN` 处理（`i18n/__init__.py:64-78`）。因此旧配置的缓存内容与其他消费方看到的字典形状不变。加载验证测试与真实子进程预检分别覆盖默认值、非法值和合法值。
2. **公开接口**：`SUPPORTED_LANGUAGES`、`get_language()`、`t(key, **kwargs)` 均按要求导出。测试直接导入并调用这些名称；后续消费者若改名会在测试收集或调用时失败。
3. **缺 key 与占位符**：`t()` 只查当前语言目录，缺 key 重新抛 `KeyError`，没有 key 本身或另一语言的回落路径（`i18n/__init__.py:106-111`）；`str.format(**kwargs)` 对缺少命名参数抛 `KeyError`。单测覆盖两种错误，且反向验证确认缺 key 断言会转红。
4. **目录一致性**：`test_locale_files_have_identical_key_sets` 比较所有受支持目录的完整 key 集合，并拒绝空目录与空文案。
5. **依赖与既有文案**：提交区间没有依赖清单变更；没有改动既有用户可见文案，只新增两份 locale 文件。未引入 gettext/Babel。

## 调用频率与缓存

`get_language()` 每次调用 `load_config()`，但常规路径由 `logger.py:53-55` 直接返回进程内配置缓存；不会每次读配置文件。之后是两项 tuple 成员检查。`t()` 的 locale JSON 每种语言首次使用时读取一次并存入 `_catalogs`，后续只有字典查找与格式化。该路径适合高频渲染调用。`load_config` 原有缓存早返回和 `use_cache` 写缓存语义未改变；新增校验只在新解析配置时执行。

## Finding

### F1 — 不变式候选，P3，非阻断

- **位置**：`src/video_transcript_api/i18n/__init__.py:81-89`（`_catalog` 仅由 `t()` 调用）；`tests/unit/i18n/test_i18n.py:63-66`（`_read_catalog` 仅由 key 集合测试调用）。
- **对应约束**：仓库反过度设计约束要求新增 helper 有第二个消费者或既有失败依据；本条不是 design.md 的行为不变式，按“不变式候选”列出。
- **触发条件**：当前只有上述各自一个调用点，未发现先前失败需要保留该层。`_catalog` 的缓存本身有高频调用的性能理由，但取缓存与读文件的单消费者 helper 可内联到 `t()`；测试中的 JSON 读取也只有一个消费者。
- **影响与处置**：增加少量导航与维护间接层，不造成运行时错误或用户可见差异。可在后续小改动中内联；不阻断 C1 交付。

## 验证记录

- `uv run --frozen pytest -q tests/unit/i18n`：退出码 0，13 个测试全部通过（输出到 `[100%]`；只有依赖弃用告警）。
- `make test`：退出码 0，完整本地测试到 `[100%]`；只有依赖与既有用例的弃用告警。
- **卡面 base 抽查**：在 `c2fa382e18734a0da410fdec1912da4c7b6c26d2` 临时 worktree 仅拷入 `tests/unit/i18n/test_i18n.py` 后运行。原始结果为收集阶段错误：

  ```text
  ImportError while importing test module '/tmp/vta-c1-red.VA7vnG/wt/tests/unit/i18n/test_i18n.py'.
  tests/unit/i18n/test_i18n.py:22: in <module>
      from video_transcript_api.i18n import (
  E   ModuleNotFoundError: No module named 'video_transcript_api.i18n'
  ERROR tests/unit/i18n/test_i18n.py
  Interrupted: 1 error during collection
  pytest_exit=2
  ```

  base 尚无被测 i18n 包，所以该抽查不能证明断言约束力；临时 worktree 已删除。
- **断言红验**：在 H0 临时 worktree 只把 `t()` 缺 key 分支改成 `return key`，运行 `test_t_raises_on_missing_key`。失败类型是断言失败，不是导入/语法错误；原实现已逐行还原，worktree 已删除。原始转红输出：

  ```text
  outbound network guard installed: socket.connect/socket.connect_ex block non-loopback AF_INET/AF_INET6 targets; DNS, loopback, and Unix-domain sockets are allowed
  F                                                                        [100%]
  =================================== FAILURES ===================================
  E   Failed: DID NOT RAISE <class 'KeyError'>
  ---------------------------- Captured stdout setup -----------------------------
  2026-10-19 19:56:53 | INFO     | wecom_notifier.platforms.wecom.notifier:__init__:117 - WeComNotifier initialized
  2026-10-19 19:56:53 | INFO     | video_transcript_api.utils.notifications.wechat:init_global_notifier:25 - 全局 WeComNotifier 实例已初始化
  2026-10-19 19:56:53 | INFO     | wecom_notifier.platforms.feishu.notifier:__init__:111 - FeishuNotifier initialized
  2026-10-19 19:56:53 | INFO     | video_transcript_api.utils.notifications.channel:init_global_feishu_notifier:29 - Global FeishuNotifier initialized
  2026-10-19 19:56:53 | INFO     | video_transcript_api.utils.notifications.router:_init_channels_from_config:31 - [router] WeChat channel initialized
  2026-10-19 19:56:53 | INFO     | video_transcript_api.utils.notifications.router:_init_channels_from_config:47 - [router] Active channels: ['wechat']
  /tmp/vta-c1-mutation.jqX9bD/wt/tests/unit/i18n/test_i18n.py:167: Failed: DID NOT RAISE <class 'KeyError'>
  =========================== short test summary info ============================
  FAILED tests/unit/i18n/test_i18n.py::test_t_raises_on_missing_key - Failed: D...
  pytest_exit=1
  ```

## OCR 初筛与处置

`ocr-review` 返回 `reviewed_fallback`（主腿 minimax 在 900 秒超时，deepseek 备链完成），给出一条占位符异常诊断信息候选。按本仓契约复核：命名占位符拼写错误会抛 `KeyError`，缺少 kwargs 也抛 `KeyError`；位置占位符 `{}` 不属于文档约定的命名占位符格式，会抛 `IndexError`，仍然是显式失败。契约只要求缺参抛错，没有要求异常重包或包含 locale key 的错误文本，因此不作为 finding，也不建议新增 catch。

实际探针输出：

```text
'{langauge}': KeyError: 'langauge'
'{}': IndexError: Replacement index 0 out of range for positional args tuple
```

## Backlog

无存量运行时问题。F1 是本次新增的 P3 结构候选，不影响契约验收。
