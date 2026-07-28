"""Single normalization contract for all per-request LLM feature gates."""

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, StrictBool


class ProcessingOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    calibrate: StrictBool = Field(True, description="Run LLM calibration")
    summarize: StrictBool = Field(True, description="Generate summary and related metadata")
    infer_speaker_names: StrictBool = Field(True, description="Infer real speaker names")
    # None inherits the global contradiction_scan_enabled config; explicit task
    # values override it without affecting the other feature gates.
    contradiction_scan: Optional[StrictBool] = Field(
        None, description="Run semantic contradiction scan"
    )
    # Optional: when the request omits this field, normalize_processing_options()
    # follows the effective summarize value. Do NOT default to True here — that
    # would make legacy {calibrate:false, summarize:false} clients still pay for
    # chapters generation (design §5.2 / R2).
    chapters: Optional[StrictBool] = Field(
        None,
        description=(
            "Generate chapter outline. When omitted (None), follows summarize after "
            "normalization. Explicit true/false is preserved as-is."
        ),
    )


def normalize_processing_options(value: Any = None) -> dict[str, bool]:
    """Return a fresh, complete, strictly validated feature-gate mapping.

    ``chapters`` follows the normalized ``summarize`` value when the request
    did not specify it (model field is None). Explicit true/false is kept.
    """
    if value is None:
        data = ProcessingOptions().model_dump()
    elif isinstance(value, ProcessingOptions):
        data = value.model_dump()
    else:
        data = ProcessingOptions.model_validate(value).model_dump()

    if data.get("chapters") is None:
        data["chapters"] = bool(data.get("summarize", True))
    # Keep legacy normalized task payloads compact when the new optional gate
    # is omitted. Missing and explicit None both mean "inherit config".
    if data.get("contradiction_scan") is None:
        data.pop("contradiction_scan", None)
    return data


# Normalized default: all gates True, including chapters (because summarize=True).
DEFAULT_PROCESSING_OPTIONS = normalize_processing_options(None)
