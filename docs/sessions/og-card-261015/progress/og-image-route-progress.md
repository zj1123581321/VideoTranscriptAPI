# OG 出图路由（og-image-route）进度

Task: 分享卡片出图——Pillow 渲染模块 + `/og/{view_token}.png` + 生产依赖与中文字体
Dispatch: dlg-20261015-161551-bd7bb2

---

## 段1：渲染模块 + 单测 + 字体 fixture

- 当前阶段：implementing
- 本段结论：`utils/rendering/og_card.py` 完成（契约读取 `load_share_card`、折行 `wrap_text`、截断 `truncate_lines`、渲染 `render_og_card`，原子写 PNG）；`tests/og_card/test_og_card.py` 21 条全绿。字体 fixture 用 google/fonts 的 Noto Sans SC 可变字体 instancer 到 wght=400/700 后 pyftsubset，单文件 50KB（<300KB 红线），字形覆盖 = tests/og_card/*.py 全部非 ASCII 字符 + ASCII 可打印集，重生成脚本 `fonts/build_subsets.py` 随 fixture 入库。
- 关键决策与已否决方案：源字体不用本机 camoufox 缓存里的 NotoSansSC-Regular.otf（来源不明、无 Bold），改从 google/fonts 官方仓下载可变字体现场实例化，provenance 干净且两个 weight 同源；`generated_at` 只做「存在则必须是字符串」的宽松校验（B 卡无消费者，强校验只加失败模式不加价值）；字体缺失 fail-loud 抛 FileNotFoundError 不降级（卡面锁定）；ttc 集合自动选 SC face（Debian NotoSansCJK-*.ttc 的 face 0 是 JP 变体，中文会出现日式字形）。
- 下一步唯一动作：实现 `/og/{view_token}.png` 路由与路由测试。
