"""Single-call semantic contradiction scanning for speaker assignments."""

import json
from typing import Any, Dict, List, Optional

from ...utils.logging import setup_logger
from ..prompts import (
    CONTRADICTION_SCAN_SYSTEM_PROMPT,
    build_contradiction_scan_user_prompt,
)
from ..prompts.schemas.contradiction_scan import CONTRADICTION_SCAN_SCHEMA
from .llm_client import LLMClient

logger = setup_logger(__name__)


class ContradictionScanner:
    """Scan final segment IDs for semantic speaker-assignment contradictions."""

    REASONS = frozenset(
        {
            "direct_address_conflict",
            "self_reference_conflict",
            "third_person_conflict",
            "qa_adjacency_conflict",
        }
    )

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
        """Run one mocked/real LLM scan and return safe overrides plus risk flags."""
        try:
            prepared_dialogs = self._prepare_dialogs(dialogs)
            known_ids = {
                item["segment_id"]
                for item in prepared_dialogs
                if item.get("segment_id")
            }
            dialogs_text = "\n".join(
                json.dumps(item, ensure_ascii=False, sort_keys=True)
                for item in prepared_dialogs
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
            payload = response.structured_output
            entries = self._extract_entries(payload)
            overrides = self._build_overrides(entries, known_ids)
            flags: List[str] = []
            total_dialogs = len(known_ids)
            suspect_count = len(overrides)
            suspect_ratio = suspect_count / total_dialogs if total_dialogs else 0.0
            if total_dialogs and suspect_ratio > 0.20:
                overrides = {}
                flags.append("semantic_scan_unreliable")
            elif suspect_count >= 3 or suspect_ratio >= 0.03:
                flags.append("semantic_contradiction_detected")
            return {
                "status": "completed",
                "segment_overrides": overrides,
                "speaker_risk_flags": flags,
            }
        except Exception as exc:
            logger.warning(f"Contradiction scan failed; continuing without overrides: {exc}")
            return {
                "status": "failed",
                "segment_overrides": {},
                "speaker_risk_flags": [],
            }

    @staticmethod
    def _prepare_dialogs(dialogs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Keep only prompt fields and cap text to the first 100 characters."""
        prepared: List[Dict[str, Any]] = []
        for dialog in dialogs or []:
            if not isinstance(dialog, dict):
                continue
            segment_id = dialog.get("segment_id")
            if not segment_id:
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
        self, entries: List[Dict[str, Any]], known_ids: set[str]
    ) -> Dict[str, Dict[str, Any]]:
        """Build the restricted override contract and reject hallucinated evidence."""
        overrides: Dict[str, Dict[str, Any]] = {}
        allowed_fields = {"segment_id", "reason", "evidence_segment_ids"}
        for entry in entries:
            if set(entry) != allowed_fields:
                logger.warning("Contradiction scan dropped entry with unknown fields")
                continue
            segment_id = entry.get("segment_id")
            reason = entry.get("reason")
            evidence = entry.get("evidence_segment_ids")
            if (
                not isinstance(segment_id, str)
                or segment_id not in known_ids
                or reason not in self.REASONS
                or not isinstance(evidence, list)
                or not evidence
                or any(not isinstance(item, str) or item not in known_ids for item in evidence)
            ):
                if isinstance(evidence, list) and any(
                    isinstance(item, str) and item not in known_ids for item in evidence
                ):
                    logger.warning(
                        "Contradiction scan dropped entry with unknown evidence segment id"
                    )
                continue
            if segment_id in overrides:
                continue
            overrides[segment_id] = {
                "status": "suspect",
                "assignment_source": "semantic_evidence",
                "reason": reason,
                "evidence_segment_ids": list(dict.fromkeys(evidence)),
            }
        return overrides
