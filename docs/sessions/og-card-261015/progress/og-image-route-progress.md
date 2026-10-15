# OG 出图路由（og-image-route）进度

Task: 分享卡片出图——Pillow 渲染模块 + `/og/{view_token}.png` + 生产依赖与中文字体
Dispatch: dlg-20261015-161551-bd7bb2

---

## 段1：渲染模块 + 单测 + 字体 fixture

- 当前阶段：implementing
- 本段结论：`utils/rendering/og_card.py` 完成（契约读取 `load_share_card`、折行 `wrap_text`、截断 `truncate_lines`、渲染 `render_og_card`，原子写 PNG）；`tests/og_card/test_og_card.py` 21 条全绿。字体 fixture 用 google/fonts 的 Noto Sans SC 可变字体 instancer 到 wght=400/700 后 pyftsubset，单文件 50KB（<300KB 红线），字形覆盖 = tests/og_card/*.py 全部非 ASCII 字符 + ASCII 可打印集，重生成脚本 `fonts/build_subsets.py` 随 fixture 入库。
- 关键决策与已否决方案：源字体不用本机 camoufox 缓存里的 NotoSansSC-Regular.otf（来源不明、无 Bold），改从 google/fonts 官方仓下载可变字体现场实例化，provenance 干净且两个 weight 同源；`generated_at` 只做「存在则必须是字符串」的宽松校验（B 卡无消费者，强校验只加失败模式不加价值）；字体缺失 fail-loud 抛 FileNotFoundError 不降级（卡面锁定）；ttc 集合自动选 SC face（Debian NotoSansCJK-*.ttc 的 face 0 是 JP 变体，中文会出现日式字形）。
- 下一步唯一动作：生产依赖（Pillow 移入 [project].dependencies）、Dockerfile 字体、config.example、样图。

---

## 段2：/og/{view_token}.png 路由

- 当前阶段：implementing
- 本段结论：views.py 新增 `GET /og/{view_token}.png`（include_in_schema=False）：ViewTokenResolver 解 token → load_share_card 读卡 → og_card.png 比 json 新则直接回缓存、否则重渲染原子覆盖后返回，Content-Type image/png；token 无缓存/无卡/卡不合契约一律 404。路由测试 8 条全绿（含缓存命中哨兵字节断言、json 更新重渲染、404 三态、/view 与 /og 互不吞、字体缺失 500 fail-loud）。
- 关键决策与已否决方案：缓存新鲜度用 st_mtime_ns 整数比较（浮点 st_mtime 有精度坑）；渲染抖动不加锁——两个并发请求同时 miss 各自渲染，os.replace 原子覆盖后两者都是合法 PNG，幂等无需串行化；平台展示名把 generate_download_filename 内的局部 dict 提升为模块常量 _PLATFORM_DISPLAY_MAP 复用（第二个消费者即本路由，非新抽象）；测试用 os.utime 显式设置 mtime 消除文件系统时间戳粒度不确定性。
- 下一步唯一动作：生产依赖（Pillow 移入 [project].dependencies）、Dockerfile 字体、config.example、样图。

---

## 段3：生产依赖 + 字体部署 + 样图

- 当前阶段：verifying
- 本段结论：pillow 从 [dependency-groups].dev 移入 [project].dependencies，uv.lock 同步（组间迁移，版本不变 12.3.0）；Dockerfile apt 增加 fonts-noto-cjk；config.example.jsonc web 段新增 og_font_path/og_font_bold_path（Debian Noto CJK 默认路径，commentjson 解析验证通过）。样图 og-card-sample.png 入库。测试 29 条全绿。
- 关键决策与已否决方案：踩了一个真坑——字体子集先生成、SAMPLE_CARD 后写，样图首次出现大片空 glyph；修法是把子集脚本的字形扫描源扩为 tests/og_card/*.py + 渲染器源码（含「AI 总结」字面量），并在脚本 docstring 写明「新增中文必须重跑」；否决了手工维护字形清单（会漂移）。样图目检确认：标题两行折行、中英文混排、序号、域名与 AI 总结 均正常。
- 下一步唯一动作：全量回归（make test）、红验、docker 构建验证 fc-list、推送开 draft PR。

---

## 段4：验证收尾

- 当前阶段：verifying
- 本段结论：全量回归 4035 passed / 3 skipped（存量） / 1 failed——唯一失败 test_unix_domain_socket_is_not_blocked 为继承环境红（派发框架 TMPDIR 长 109 字符超 AF_UNIX 108 上限），已在 base 552f496e 独立 worktree 复现同错，与本卡无关。红验：改坏 truncate_lines 省略号拼接 → 2 条断言失败转红（AssertionError），还原后 29 条全绿。docker 构建成功，镜像内字体文件与配置路径一致，fc-list（临时容器补装 fontconfig）确认 NotoSansCJK-Regular/Bold.ttc 均含 SC face；容器内用生产默认字体路径端到端渲染 1200x630 PNG 成功。
- 关键决策与已否决方案：继承红判定依据=base 复现 + 测试与守卫代码均早于 base（d9f2e2c6 是 552f496e 祖先）+ 失败路径与本卡改动零交集；主干基线不可用（gh api failed），故继承红以本地 base 复现取证。
- 下一步唯一动作：推送分支、开 draft PR、写报告。

---

## 段5：门禁主审修复（F1-F4）

- 当前阶段：verifying
- 本段结论：先 merge origin/main（A 卡入库，无冲突），29 条存量测试绿。F1 load_share_card 严格校验：version==SHARE_CARD_FORMAT_VERSION、headline/points 复用 A 卡 _validate_card（同源长度权重规则）、generated_at 必须非空 ISO8601；F2 Cache-Control 收紧为 max-age=300；F3 缓存新鲜度 stat 窗口的 FileNotFoundError 转 404+warning；F4 顶栏与域名经 layout_header/layout_footer_host 截断防溢出。测试 29→47 条全绿；F1/F3 各一次单行注入红验均转 AssertionError 红，还原只改该行。样图重生成后与上轮字节一致（正常输入不触发 F4 截断，本身即无回归证据）。
- 关键决策与已否决方案：否决「try 包住整个 render+stat」方案——字体缺失也是 FileNotFoundError，会被静默吞成 404，破坏「字体缺失必须 fail loud」锁定决策（实测 test_missing_font_fails_loud 转 404 暴露此问题），改为只包 stat 窗口；否决重写长度判定，直接 import A 卡 _validate_card（feedback 指示复用）。uv.lock 顺带把自版本号 1.1.0 同步为 pyproject 的 1.2.0（main 上已失步，本卡 uv run 重解析暴露，在 Scope 内）。
- 下一步唯一动作：全量回归（make test）、推送、更新报告。

---

## 段6：门禁主审第2轮修复（G1/G2）

- 当前阶段：verifying
- 本段结论：G1 出图路由弃用 FileResponse（发送阶段才 stat/打开文件，重新总结删 png 会 500），改为 handler 内 read_bytes 后返回 Response，读取窗口 FileNotFoundError→404+warning，render 不在 try 内（字体缺失保持 500 fail loud）；G2 build_subsets.py 扫描源补 views.py（平台显示名 _PLATFORM_DISPLAY_MAP 的汉字入子集），子集 62KB→141KB，新增 fontTools cmap 覆盖断言测试（fontTools>=4.53.0 进 dev 依赖），样图随新子集重新渲染入库（版式不变，字形 hinting 微差 0.57% 像素）。测试 47→51 条全绿；G1/G2 各一次单行注入红验均转 AssertionError，还原只改该行。OFL.txt 与上游 ofl/notosanssc/OFL.txt 逐字节一致，主审误报，不改。
- 关键决策与已否决方案：否决「从 _PLATFORM_DISPLAY_MAP 取值需 import views」方案——views.py 顶层 get_templates()/get_static_dir() 非惰性，独立脚本直跑有副作用，改扫文件文本无副作用；发现并修正 fontTools cmap 表 key 是码点 int 而非字符（首版断言全误报）；预算超 hard（base..head 1304 行 > 1200）：feedback 追加 G1/G2 必修 + fontTools 依赖（uv.lock +67 行）所致，文本增量仅 +78 行，由主脑裁决。
- 下一步唯一动作：推送分支（只推一次）、写报告。
