"""Windowed semantic contradiction scanning for speaker assignments."""

import json
from typing import Any, Dict, List, Optional

from ...utils.logging import setup_logger
from ..prompts import (
    CONTRADICTION_SCAN_SYSTEM_PROMPT,
    build_contradiction_scan_user_prompt,
)
from ..prompts.schemas.contradiction_scan import (
    CONTRADICTION_REASONS,
    CONTRADICTION_SCAN_SCHEMA,
)
from .llm_client import LLMClient

logger = setup_logger(__name__)
# Semantic scan window size and overlap. The overlap preserves context while
# keeping each LLM request bounded; windows advance by 390 segments.
SCAN_WINDOW_SEGMENTS = 400
SCAN_WINDOW_OVERLAP = 10


class ContradictionScanner:
    """Scan final segment IDs for semantic speaker-assignment contradictions."""

    REASONS = frozenset(CONTRADICTION_REASONS)

    def __init__(
        self,
        llm_client: LLMClient,
        model: str = "calibrate-model",
        reasoning_effort: Optional[str] = None,
    ) -> None:
        self.llm_client = llm_client
        self.model = model
        self.reasoning_effort = reasoning_effort

    def scan_contradictions(
        self,
        dialogs: List[Dict[str, Any]],
        speaker_mapping: Dict[str, str],
        speaker_inference_meta: Dict[str, Any],
        title: str = "",
        description: str = "",
        selected_models: Optional[Dict[str, Any]] = None,
        video_title: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Scan all prepared dialogs in overlapping windows and merge safely."""
        prepared_dialogs = self._prepare_dialogs(dialogs)
        known_ids = {
            item["segment_id"] for item in prepared_dialogs if item.get("segment_id")
        }
        if not prepared_dialogs:
            return {
                "status": "completed",
                "segment_overrides": {},
                "speaker_risk_flags": [],
            }

        step = SCAN_WINDOW_SEGMENTS - SCAN_WINDOW_OVERLAP
        merged_overrides: Dict[str, Dict[str, Any]] = {}
        for window_index, start in enumerate(range(0, len(prepared_dialogs), step), 1):
            end = min(start + SCAN_WINDOW_SEGMENTS, len(prepared_dialogs))
            window_dialogs = prepared_dialogs[start:end]
            try:
                window_overrides = self._scan_window(
                    window_dialogs=window_dialogs,
                    known_ids=known_ids,
                    speaker_mapping=speaker_mapping,
                    speaker_inference_meta=speaker_inference_meta,
                    title=title,
                    description=description,
                    selected_models=selected_models,
                    video_title=video_title,
                )
            except Exception as exc:
                logger.warning(f"Contradiction scan failed for window {window_index}: {exc}")
                return {
                    "status": "failed",
                    "segment_overrides": {},
                    "speaker_risk_flags": [],
                }
            for segment_id, override in window_overrides.items():
                # Windows overlap intentionally; first-seen target wins.
                if segment_id not in merged_overrides:
                    merged_overrides[segment_id] = override
            if end >= len(prepared_dialogs):
                break

        flags: List[str] = []
        total_dialogs = len(known_ids)
        suspect_count = len(merged_overrides)
        suspect_ratio = suspect_count / total_dialogs if total_dialogs else 0.0
        if total_dialogs and suspect_ratio > 0.20:
            merged_overrides = {}
            flags.append("semantic_scan_unreliable")
        elif suspect_count >= 3 or (
            total_dialogs and suspect_ratio >= 0.03
        ):
            flags.append("semantic_contradiction_detected")
        return {
            "status": "completed",
            "segment_overrides": merged_overrides,
            "speaker_risk_flags": flags,
        }

    def _scan_window(
        self,
        *,
        window_dialogs: List[Dict[str, Any]],
        known_ids: set[str],
        speaker_mapping: Dict[str, str],
        speaker_inference_meta: Dict[str, Any],
        title: str,
        description: str,
        selected_models: Optional[Dict[str, Any]],
        video_title: Optional[str],
    ) -> Dict[str, Dict[str, Any]]:
        """Call the LLM once for a window and validate its entries."""
        target_ids = {item["segment_id"] for item in window_dialogs}
        dialogs_text = "\n".join(
            json.dumps(item, ensure_ascii=False, sort_keys=True)
            for item in window_dialogs
        )
        user_prompt = build_contradiction_scan_user_prompt(
            dialogs_text=dialogs_text,
            speaker_mapping=speaker_mapping,
            speaker_inference_meta=speaker_inference_meta,
            video_title=title if video_title is None else video_title,
            description=description,
        )
        model = self.model
        reasoning_effort = self.reasoning_effort
        if selected_models:
            model = selected_models.get("speaker_model") or model
            reasoning_effort = (
                selected_models.get("speaker_reasoning_effort") or reasoning_effort
            )
        if not model:
            raise ValueError("Contradiction scan model is not configured")
        response = self.llm_client.call(
            model=model,
            system_prompt=CONTRADICTION_SCAN_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            response_schema=CONTRADICTION_SCAN_SCHEMA,
            reasoning_effort=reasoning_effort,
            task_type="speaker_contradiction_scan",
        )
        entries = self._extract_entries(response.structured_output)
        return self._build_overrides(entries, target_ids, known_ids)

    @staticmethod
    def _prepare_dialogs(dialogs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Keep only prompt fields and cap text to the first 100 characters."""
        prepared: List[Dict[str, Any]] = []
        skipped_missing_segment_id = 0
        for dialog in dialogs or []:
            if not isinstance(dialog, dict):
                continue
            segment_id = dialog.get("segment_id")
            if not segment_id:
                skipped_missing_segment_id += 1
                continue
            prepared.append(
                {
                    "segment_id": str(segment_id),
                    "display_name": str(dialog.get("speaker") or ""),
                    "speaker_id": str(
                        dialog.get("speaker_id")
                        if dialog.get("speaker_id") is not None
                        else ""
                    ),
                    "text": str(dialog.get("text") or "")[:100],
                }
            )
        if skipped_missing_segment_id:
            logger.warning(f"Contradiction scan skipped {skipped_missing_segment_id} dialogs without segment_id")
        return prepared

    def _extract_entries(self, payload: Any) -> List[Dict[str, Any]]:
        """Validate the structured envelope before processing individual entries."""
        if not isinstance(payload, dict):
            raise ValueError("Contradiction scan response is not an object")
        if set(payload) - {"contradictions"}:
            raise ValueError("Contradiction scan response has unknown fields")
        entries = payload.get("contradictions")
        if not isinstance(entries, list):
            raise ValueError("Contradiction scan response has invalid contradictions")
        if any(not isinstance(entry, dict) for entry in entries):
            raise ValueError("Contradiction scan response has malformed contradiction")
        return entries

    def _build_overrides(
        self,
        entries: List[Dict[str, Any]],
        target_ids: set[str],
        known_ids: set[str],
    ) -> Dict[str, Dict[str, Any]]:
        """Build the restricted override contract and reject hallucinated evidence."""
        overrides: Dict[str, Dict[str, Any]] = {}
        allowed_fields = {"segment_id", "reason", "evidence_segment_ids"}
        for entry in entries:
            segment_id = entry.get("segment_id")
            if set(entry) != allowed_fields:
                logger.warning(f"Contradiction scan dropped entry for segment_id {segment_id!r}: field set mismatch")
                continue
            reason = entry.get("reason")
            evidence = entry.get("evidence_segment_ids")
            if not isinstance(segment_id, str) or segment_id not in target_ids:
                logger.warning(f"Contradiction scan dropped entry for segment_id {segment_id!r}: target id hallucination")
                continue
            if not isinstance(reason, str) or reason not in self.REASONS:
                logger.warning(f"Contradiction scan dropped entry for segment_id {segment_id!r}: reason is illegal ({reason!r})")
                continue
            if not isinstance(evidence, list) or not evidence:
                logger.warning(f"Contradiction scan dropped entry for segment_id {segment_id!r}: evidence fields are malformed")
                continue
            if any(not isinstance(item, str) or item not in known_ids for item in evidence):
                logger.warning(f"Contradiction scan dropped entry for segment_id {segment_id!r}: evidence segment id hallucination")
                continue
            if segment_id in overrides:
                logger.warning(f"Contradiction scan dropped entry for segment_id {segment_id!r}: duplicate id")
                continue
            overrides[segment_id] = {
                "status": "suspect",
                "assignment_source": "semantic_evidence",
                "reason": reason,
                "evidence_segment_ids": list(dict.fromkeys(evidence)),
            }
        return overrides
