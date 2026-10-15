"""分享卡片文案 Schema 与 Prompt 定义（og 大图卡片，卡 A）。

总结成功后另发一次小的大模型调用，产出分享卡片文案
（吸睛标题 + 最多 3 条要点），由 ShareCardProcessor 校验后落盘为
llm_share_card.json。契约（A 写、B 读，字段名与含义不得改动）：
{"version": 1, "headline": str, "points": [str, ...], "generated_at": ISO8601}
"""

# 关键内容权重长度上限（1 个 CJK 字符计 1，其余字符计 0.5，
# 纯英文文本因此自动获得 2 倍字符数上限，与落盘契约表述一致）：
# headline ≤30 个汉字（英文 ≤60 字符），每条要点 ≤40 个汉字（英文 ≤80 字符）。
SHARE_CARD_HEADLINE_MAX_UNITS = 30
SHARE_CARD_POINT_MAX_UNITS = 40

# 喂给模型的总结正文最大字符数（超长截断；总结正文篇幅预算通常远小于此值）。
SHARE_CARD_MAX_SUMMARY_CHARS = 6000

# 落盘契约版本号（llm_share_card.json 的 "version" 字段）。
SHARE_CARD_FORMAT_VERSION = 1

# 分享卡片输出的 JSON Schema（结构化输出约束；处理器仍会做严格后验校验，
# 不信任模型一定遵守 schema）。
SHARE_CARD_SCHEMA = {
    "type": "object",
    "properties": {
        "headline": {
            "type": "string",
            "description": "吸睛标题：一眼就想点开的一句话，不超过 30 个汉字"
            "（英文不超过 60 个字符），单行纯文本，不加引号或书名号",
        },
        "points": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 1,
            "maxItems": 3,
            "description": "内容要点：从总结中提炼的 1-3 条关键信息，"
            "每条不超过 40 个汉字（英文不超过 80 个字符），单行纯文本",
        },
    },
    "required": ["headline", "points"],
}

SHARE_CARD_SYSTEM_PROMPT = """你是一位社交媒体内容编辑。你的任务是根据一份视频内容的 AI 总结，为分享卡片提炼文案。这份文案会显示在一张信息密集型的分享大图上，读者扫一眼就要知道这期内容讲什么，并被吸引点开。

## 输出要求

1. **headline（吸睛标题）**：
   - 一句话，制造好奇心或点明最大亮点，但不做标题党式的虚假承诺。
   - 不超过 30 个汉字（英文内容不超过 60 个字符）。
   - 单行纯文本：不加引号、书名号、句号，不用 emoji，不分行。

2. **points（内容要点）**：
   - 1 到 3 条，按重要性排序，宁可少而精。
   - 每条是一个完整的短句，不超过 40 个汉字（英文内容不超过 80 个字符）。
   - 单行纯文本：不用 emoji、不用序号前缀、不分行。

3. **语言**：与总结正文的语言保持一致（中文总结出中文文案，英文总结出英文文案）。

4. **忠于原文**：只从总结内容中提炼，不要编造总结里没有的信息。"""


def build_share_card_user_prompt(
    *,
    summary_text: str,
    title: str,
    author: str = "",
    platform: str = "",
) -> str:
    """构建分享卡片文案的用户 Prompt。

    Args:
        summary_text: 总结正文（超长时截断到 SHARE_CARD_MAX_SUMMARY_CHARS）。
        title: 视频标题。
        author: 作者/频道名。
        platform: 平台标识。

    Returns:
        用户 Prompt 字符串。
    """
    truncated = summary_text[:SHARE_CARD_MAX_SUMMARY_CHARS]
    if len(summary_text) > SHARE_CARD_MAX_SUMMARY_CHARS:
        truncated += "\n...(truncated)"
    meta_lines = [f"视频标题：{title}"]
    if author:
        meta_lines.append(f"作者：{author}")
    if platform:
        meta_lines.append(f"平台：{platform}")
    return (
        "以下是视频的元数据与 AI 总结正文，请提炼分享卡片文案。\n\n"
        + "\n".join(meta_lines)
        + f"\n\n## 总结正文\n\n{truncated}"
    )
