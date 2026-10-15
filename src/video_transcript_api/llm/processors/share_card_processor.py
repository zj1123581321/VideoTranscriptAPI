"""Share card copy processor (og large-image card, card A).

Runs one small LLM call after the summary has been generated, distils an
eye-catching headline plus 1-3 key points from the summary body, validates
them against the share-card contract and returns the payload that
llm_ops persists as ``llm_share_card.json``.

Failure isolation (card requirement): this processor never raises. Any
exception is converted into ``ShareCardResult(card=None, error=...)`` so a
failed share-card round can never flip the task's terminal status or
affect the summary artifact.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Optional

from ...utils.logging import setup_logger
from ..core.config import LLMConfig
from ..core.llm_client import LLMClient
from ..prompts.schemas.share_card import (
    SHARE_CARD_FORMAT_VERSION,
    SHARE_CARD_HEADLINE_MAX_UNITS,
    SHARE_CARD_POINT_MAX_UNITS,
    SHARE_CARD_SCHEMA,
    SHARE_CARD_SYSTEM_PROMPT,
    build_share_card_user_prompt,
)

logger = setup_logger(__name__)

# CJK Unified Ideographs + Extension A + Compatibility Ideographs.
_CJK_RANGES = (
    (0x4E00, 0x9FFF),
    (0x3400, 0x4DBF),
    (0xF900, 0xFAFF),
)


def _is_cjk_char(ch: str) -> bool:
    code = ord(ch)
    return any(lo <= code <= hi for lo, hi in _CJK_RANGES)


def _effective_length(text: str) -> float:
    """Contract length: a CJK char counts 1, any other char counts 0.5.

    Pure-ASCII text therefore gets exactly twice the character budget,
    which matches the contract wording "≤30 汉字（英文 ≤60 字符）".
    """
    return sum(1.0 if _is_cjk_char(ch) else 0.5 for ch in text)


def _validate_card(data: Dict) -> Optional[str]:
    """Validate a model-produced card dict against the contract.

    Returns:
        None when the card is contract-valid, otherwise a human-readable
        failure reason (logged upstream together with task_id).
    """
    headline = data.get("headline")
    if not isinstance(headline, str) or not headline.strip():
        return f"headline missing or empty: {type(headline).__name__}"
    if _effective_length(headline) > SHARE_CARD_HEADLINE_MAX_UNITS:
        return (
            f"headline too long: effective_length="
            f"{_effective_length(headline):.1f} > {SHARE_CARD_HEADLINE_MAX_UNITS}"
        )

    points = data.get("points")
    if not isinstance(points, list) or not (1 <= len(points) <= 3):
        return f"points must be a list of 1..3 items, got {type(points).__name__}"
    for i, point in enumerate(points):
        if not isinstance(point, str) or not point.strip():
            return f"points[{i}] missing or empty: {type(point).__name__}"
        if _effective_length(point) > SHARE_CARD_POINT_MAX_UNITS:
            return (
                f"points[{i}] too long: effective_length="
                f"{_effective_length(point):.1f} > {SHARE_CARD_POINT_MAX_UNITS}"
            )
    return None


@dataclass(frozen=True)
class ShareCardResult:
    """分享卡片生成结果（失败隔离载体，模式同 SummaryResult）。

    card 仅在 error 为 None 时非空；error 携带失败原因原文，
    由上层（llm_ops）连同 task_id 一起记入 error 日志。
    """

    card: Optional[Dict]
    error: Optional[str]


class ShareCardProcessor:
    """分享卡片文案处理器

    职责：
    - 基于总结正文生成分享卡片文案（吸睛标题 + 要点）
    - 模型复用 summary_model / summary_reasoning_effort 配置
      （含风控覆盖：selected_models 的覆盖逻辑与总结一致）
    - 按 llm_share_card.json 契约严格校验模型输出

    失败语义：不向调用方抛出任何异常；生成失败或输出不合规时返回
    ``card=None, error=原因``，调用方记 error 日志后继续（不写文件、
    不重试、不影响任务终态）。
    """

    def __init__(self, llm_client: LLMClient, config: LLMConfig):
        self.llm_client = llm_client
        self.config = config
        logger.info("ShareCardProcessor initialized")

    def process(
        self,
        *,
        summary_text: str,
        title: str,
        author: str = "",
        platform: str = "",
        selected_models: Optional[Dict] = None,
    ) -> ShareCardResult:
        """生成分享卡片文案。

        Args:
            summary_text: 总结正文（来自本轮 GENERATED 的总结）。
            title: 视频标题。
            author: 作者/频道名。
            platform: 平台标识。
            selected_models: 风控选定的模型配置（与总结调用共用同一份）。

        Returns:
            ShareCardResult：成功时 card 为符合契约的
            ``{"version": 1, "headline": str, "points": [str, ...],
            "generated_at": ISO8601}``；失败时 card=None 且 error 说明原因。
        """
        try:
            if not isinstance(summary_text, str) or not summary_text.strip():
                return ShareCardResult(card=None, error="empty summary text")

            # 模型选择：与 SummaryProcessor 相同的覆盖逻辑（风控覆盖优先）。
            if selected_models:
                model = selected_models.get("summary_model", self.config.summary_model)
                reasoning_effort = selected_models.get(
                    "summary_reasoning_effort",
                    self.config.summary_reasoning_effort,
                )
            else:
                model = self.config.summary_model
                reasoning_effort = self.config.summary_reasoning_effort

            response = self.llm_client.call(
                model=model,
                system_prompt=SHARE_CARD_SYSTEM_PROMPT,
                user_prompt=build_share_card_user_prompt(
                    summary_text=summary_text,
                    title=title,
                    author=author,
                    platform=platform,
                ),
                response_schema=SHARE_CARD_SCHEMA,
                reasoning_effort=reasoning_effort,
                task_type="share_card",
            )

            data = response.structured_output
            if not isinstance(data, dict):
                return ShareCardResult(
                    card=None,
                    error=(
                        "structured output is not a dict: "
                        f"{type(data).__name__}"
                    ),
                )

            problem = _validate_card(data)
            if problem is not None:
                return ShareCardResult(card=None, error=problem)

            card = {
                "version": SHARE_CARD_FORMAT_VERSION,
                "headline": data["headline"].strip(),
                "points": [point.strip() for point in data["points"]],
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }
            logger.info(
                f"Share card generated (headline_length={len(card['headline'])}, "
                f"points={len(card['points'])})"
            )
            return ShareCardResult(card=card, error=None)

        except Exception as exc:
            # 卡面要求的隔离边界：分享卡片失败绝不冒泡影响任务终态。
            logger.error(f"Share card generation failed: {exc}", exc_info=True)
            return ShareCardResult(card=None, error=f"{type(exc).__name__}: {exc}")
