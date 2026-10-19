# C2 英文 README 与双语配置示例 — 进度存档

Task: 新增 `README.en.md`、中英 README 顶部互链、`config/config.example.jsonc` 注释双语化并新增顶层 `language`
Branch: `card/VideoTranscriptAPI-20261019-01`
Base: `c2fa382e18734a0da410fdec1912da4c7b6c26d2`

---

## 里程碑 1：配置示例双语化 + `language` 键（commit 70ba0cac，由 harness 代提交）

- **当前阶段**：implementing（配置示例部分完成）
- **本段结论**：`config/config.example.jsonc` 的注释全部改为中英双语，整文件一种风格——单行放得下用 `中文 / English`，放不下则「中文行后紧跟英文行」逐行对译。顶层新增 `"language": "zh-CN"` 独立段落（置于 `api` 之前，带分隔线），说明取值 `zh-CN` | `en`、缺省 `zh-CN`、非法值启动失败、控制界面文案与总结/详细笔记/章节的输出语言、企业微信与飞书通知暂不随此切换。解析结构比对只多一个顶层 `language` 键。
- **关键决策与已否决方案**：否决「拆 `config.example.en.jsonc` 双文件」——两份必然漂移；否决「`language` 放在文件末尾」——它是全局语义开关，放最前才能在通读配置前先看到。段落注释采取逐行对译而非「整段中文 + 整段英文」，以贴合卡面「中文行后紧跟英文行」的格式约束。
- **下一步唯一动作**：写 `README.en.md` 并给中英 README 加顶部互链。

## 里程碑 2：英文 README 与顶部互链（commit 70ba0cac，由 harness 代提交）

- **当前阶段**：implementing（文档部分完成）
- **本段结论**：新增英文原生写作的 `README.en.md`，覆盖项目简介、功能、外部依赖、安装（uv 与 Docker 两条路径）、最小配置（含 `"language": "en"`）、`--check-config` 预检、启动、核心 API 调用示例与端点表、项目结构、文档索引、测试与协议。`README.md` 仅两处改动：标题下加 `**中文** | [English](README.en.md)`，配置步骤补一行 `language` 说明；中文正文一字未动。
- **关键决策与已否决方案**：英文版命令与端口逐条对齐 `README.md`（提取两侧命令行做集合比对：两边差集均为空），不引入中文版没有的命令；Docker 段补一句「compose 把容器 8000 发布到宿主 8200」，因为直接照抄 `localhost:8000` 的 curl 示例在 Docker 部署下会连错端口（依据 `docker/docker-compose.yml:22`）。否决「把 README.md 正文改成英文」——中文仍是主力用户。
- **下一步唯一动作**：逐段核对双语风格一致性，并跑 `make test` / `card_scope_check.py` 收口。

## 里程碑 3：补回丢失的中文原文 + 结构/风格自检（commit d6d05d77）

- **当前阶段**：verifying
- **本段结论**：逐行比对 base 与 HEAD 的中文注释流，发现 `speaker_inference` 降级段的中文句「避免把低置信度的猜测当作确定结论展示给用户」被折进英文译句、中文读者丢失了原句；已恢复中文原文并保持「中文行后紧跟英文行」的同一风格。复查结果：中文注释流相对 base 只剩新增（`language` 段、`按钮文案`、英文行里引用的 `企业级客户`），无删除、无改写；48 个注释块全部中文英文双全，不存在单语块；`commentjson` 解析 base 与 HEAD 两版，`added=['language'] removed=[] changed=[]`。
- **关键决策与已否决方案**：中文注释流比对用 CJK 字符序列做 `difflib` 差分，而不是按行 diff——逐行 diff 会把「中文行与英文行调换顺序」误判成内容改动，CJK 字符流差分只暴露真正的中文增删改。否决「顺手把 `README.md` 里过期的 `make test` 范围描述（只跑 unit + cache）改对」——超出本卡允许的改动边界，只在报告里记为继承问题。
- **下一步唯一动作**：跑 `make test` 与 `card_scope_check.py`，把原始输出写进 report.md。
