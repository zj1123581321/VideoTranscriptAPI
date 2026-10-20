"""Pipeline wiring tests for llm_share_card.json persistence (og card A).

Covers the _save_llm_results share-card block:
- GENERATED round writes the contract-shaped file (asserted from real file
  bytes written into tmp_path, not from a mock's call args);
- share-card failure keeps the task successful: no file, stale card removed,
  error logged with task_id and reason;
- resummarize deletes the stale card first, then writes the new one;
- recalibrate-only and not-requested rounds leave the file untouched.

Console output must be English only.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from video_transcript_api.api.processing_options import normalize_processing_options
from video_transcript_api.api.services import llm_ops
from video_transcript_api.utils.llm_status import SummaryStatus

VALID_CARD = {
    "version": 1,
    "headline": "吸睛标题",
    "points": ["要点一", "要点二", "要点三"],
    "generated_at": "2026-10-15T12:00:00+00:00",
}


def _patch_cm(monkeypatch, tmp_path: Path, *, snapshot=None):
    mock_cm = llm_ops.MagicMock() if hasattr(llm_ops, "MagicMock") else None
    from unittest.mock import MagicMock

    mock_cm = MagicMock()
    mock_cm.media_lock.return_value.__enter__ = MagicMock(return_value=None)
    mock_cm.media_lock.return_value.__exit__ = MagicMock(return_value=False)
    mock_cm.get_cache.return_value = snapshot or {"file_path": str(tmp_path)}
    mock_cm.invalidate_llm_status.return_value = {}
    mock_cm.save_llm_result.return_value = True
    monkeypatch.setattr(llm_ops, "cache_manager", mock_cm)
    return mock_cm


def _coordinator_result(**overrides):
    """Coordinator return shape for _build_result_dict (not a result_dict)."""
    d = {
        "calibrated_text": "calibrated body",
        "summary_text": "summary body",
        "stats": {
            "calibration_status": "full",
            "summary_status": SummaryStatus.GENERATED,
        },
        "models_used": {},
        "share_card": dict(VALID_CARD),
        "share_card_error": None,
    }
    d.update(overrides)
    return d


def _base_result(**overrides):
    d = {
        "校对文本": "calibrated body",
        "内容总结": "summary body",
        "skip_summary": False,
        "summary_status": SummaryStatus.GENERATED,
        "stats": {"calibration_status": "full"},
        "models_used": {},
        "calibrate_success": True,
        "summary_success": True,
    }
    d.update(overrides)
    return d


def _error_messages(mock_logger) -> list[str]:
    """Collect error-level messages from a patched loguru logger, covering
    both direct .error(...) and opt(exception=True).error(...) call shapes."""
    msgs = [str(c.args[0]) for c in mock_logger.error.call_args_list]
    msgs += [
        str(c.args[0]) for c in mock_logger.opt.return_value.error.call_args_list
    ]
    return msgs


def _write_card(tmp_path: Path, card: dict) -> None:
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "llm_share_card.json").write_text(
        json.dumps(card, ensure_ascii=False), encoding="utf-8"
    )


def _run_save(monkeypatch, tmp_path: Path, result_dict: dict, **kwargs):
    _patch_cm(monkeypatch, tmp_path)
    return llm_ops._save_llm_results(
        task_id=kwargs.pop("task_id", "t-card"),
        platform="youtube",
        media_id="m1",
        use_speaker_recognition=False,
        result_dict=result_dict,
        calibrate_only=kwargs.pop("calibrate_only", False),
        **kwargs,
    )


class TestShareCardPersistence:
    def test_generated_writes_contract_file(self, monkeypatch, tmp_path):
        """GENERATED + valid card must write llm_share_card.json; the file's
        bytes must parse into exactly the contract fields."""
        result = _run_save(
            monkeypatch,
            tmp_path,
            _base_result(share_card=dict(VALID_CARD)),
        )

        card_file = tmp_path / "llm_share_card.json"
        assert card_file.exists()
        card = json.loads(card_file.read_bytes().decode("utf-8"))
        assert set(card.keys()) == {"version", "headline", "points", "generated_at"}
        assert card["version"] == 1
        assert isinstance(card["headline"], str) and card["headline"]
        assert isinstance(card["points"], list) and 1 <= len(card["points"]) <= 3
        assert result["summary_status"] == SummaryStatus.GENERATED

    def test_no_leftover_temp_files(self, monkeypatch, tmp_path):
        """The atomic write must not leave .tmp residue in the cache dir."""
        _run_save(monkeypatch, tmp_path, _base_result(share_card=dict(VALID_CARD)))

        assert list(tmp_path.glob("*.tmp")) == []
        assert list(tmp_path.glob(".*tmp*")) == []

    def test_generation_failure_removes_stale_card_and_logs_error(
        self, monkeypatch, tmp_path
    ):
        """Generated summary + failed card: stale card removed, no new file,
        error log carries task_id and reason, task still succeeds."""
        from unittest.mock import patch

        _write_card(tmp_path, {"version": 1, "headline": "old", "points": ["p"]})

        with patch("video_transcript_api.api.services.llm_ops.logger") as mock_logger:
            result = _run_save(
                monkeypatch,
                tmp_path,
                _base_result(share_card=None, share_card_error="RuntimeError: boom"),
                task_id="t-fail-card",
            )

        assert not (tmp_path / "llm_share_card.json").exists()
        assert result["summary_status"] == SummaryStatus.GENERATED
        error_messages = [
            str(call.args[0]) for call in mock_logger.error.call_args_list
        ]
        matched = [
            m for m in error_messages
            if "t-fail-card" in m and "RuntimeError: boom" in m
        ]
        assert matched, f"expected error log with task_id and reason, got: {error_messages}"

    def test_resummarize_replaces_old_card(self, monkeypatch, tmp_path):
        """Resummarize with a new valid card must overwrite the stale one."""
        _write_card(tmp_path, {"version": 1, "headline": "old headline", "points": ["old"]})

        _run_save(monkeypatch, tmp_path, _base_result(share_card=dict(VALID_CARD)))

        card = json.loads(
            (tmp_path / "llm_share_card.json").read_bytes().decode("utf-8")
        )
        assert card["headline"] == VALID_CARD["headline"]

    def test_legacy_result_dict_never_probes_cache(self, monkeypatch, tmp_path):
        """A legacy (hand-built) result_dict without the share_card key must
        not trigger a get_cache probe in a full-flow round — the layered-cache
        performance contract (no probing when all layers are requested) is
        preserved."""
        from unittest.mock import MagicMock

        mock_cm = MagicMock()
        mock_cm.media_lock.return_value.__enter__ = MagicMock(return_value=None)
        mock_cm.media_lock.return_value.__exit__ = MagicMock(return_value=False)
        mock_cm.invalidate_llm_status.return_value = {}
        mock_cm.save_llm_result.return_value = True
        monkeypatch.setattr(llm_ops, "cache_manager", mock_cm)

        llm_ops._save_llm_results(
            task_id="t-legacy",
            platform="youtube",
            media_id="m1",
            use_speaker_recognition=False,
            result_dict=_base_result(),
            calibrate_only=False,
            processing_options={
                "calibrate": True,
                "summarize": True,
                "infer_speaker_names": True,
                "chapters": True,
            },
        )

        mock_cm.get_cache.assert_not_called()

    def test_summary_failed_deletes_stale_card(self, monkeypatch, tmp_path):
        """A round that attempted the summary but FAILED must not leave the
        stale card behind (locked decision: delete first on resummarize)."""
        _write_card(tmp_path, {"version": 1, "headline": "old", "points": ["p"]})

        _run_save(
            monkeypatch,
            tmp_path,
            _base_result(summary_status=SummaryStatus.FAILED, share_card=None),
        )

        assert not (tmp_path / "llm_share_card.json").exists()

    def test_calibrate_only_preserves_card(self, monkeypatch, tmp_path):
        """Recalibrate-only round (no summary backfill) must not touch the
        card file."""
        _write_card(tmp_path, {"version": 1, "headline": "untouched", "points": ["p"]})

        _run_save(
            monkeypatch,
            tmp_path,
            _base_result(summary_status=None, share_card=None),
            calibrate_only=True,
        )

        card = json.loads(
            (tmp_path / "llm_share_card.json").read_bytes().decode("utf-8")
        )
        assert card["headline"] == "untouched"

    def test_persistence_exception_isolated_summary_and_structured_still_saved(
        self, monkeypatch, tmp_path
    ):
        """Review F1: any exception inside the card persistence section
        (get_cache / unlink / atomic write) must not escape _save_llm_results.
        The summary save and the structured save that follows the card block
        must both still run, and the error log must carry task_id and the
        exception type."""
        from unittest.mock import patch

        def _boom(path, data):
            raise OSError("disk full")

        mock_cm = _patch_cm(monkeypatch, tmp_path)
        monkeypatch.setattr(llm_ops, "_atomic_write_json", _boom)

        with patch("video_transcript_api.api.services.llm_ops.logger") as mock_logger:
            raised = None
            result = None
            try:
                result = llm_ops._save_llm_results(
                    task_id="t-f1",
                    platform="youtube",
                    media_id="m1",
                    use_speaker_recognition=False,
                    result_dict=_base_result(
                        share_card=dict(VALID_CARD),
                        structured_data={"dialogs": []},
                    ),
                    calibrate_only=False,
                    plain_structured_active=True,
                )
            except Exception as exc:  # noqa: BLE001 - this escape is the bug
                raised = exc

        assert raised is None, f"card persistence exception escaped: {raised!r}"
        llm_types = [
            c.kwargs.get("llm_type") for c in mock_cm.save_llm_result.call_args_list
        ]
        assert "summary" in llm_types, "summary save must still happen"
        assert "structured" in llm_types, (
            "structured save (after the card block) must still run"
        )
        assert result is not None
        assert result["summary_status"] == SummaryStatus.GENERATED
        assert not (tmp_path / "llm_share_card.json").exists()
        errors = "\n".join(_error_messages(mock_logger))
        assert "t-f1" in errors and "OSError" in errors, (
            f"expected error log with task_id and exception type, got: {errors}"
        )

    @pytest.mark.parametrize(
        "cache_return",
        [
            pytest.param(None, id="get_cache_returns_none"),
            pytest.param({"llm_summary": "cached"}, id="snapshot_without_file_path"),
        ],
    )
    def test_missing_cache_path_logs_error(
        self, monkeypatch, tmp_path, cache_return
    ):
        """Review F2: when the card block runs but the cache path is
        unavailable (get_cache empty or missing file_path), the generated card
        must not be dropped silently — an error log with task_id (and
        card_generated) is required; the task still succeeds."""
        from unittest.mock import patch

        mock_cm = _patch_cm(monkeypatch, tmp_path)
        mock_cm.get_cache.return_value = cache_return

        with patch("video_transcript_api.api.services.llm_ops.logger") as mock_logger:
            result = llm_ops._save_llm_results(
                task_id="t-f2",
                platform="youtube",
                media_id="m1",
                use_speaker_recognition=False,
                result_dict=_base_result(share_card=dict(VALID_CARD)),
                calibrate_only=False,
            )

        assert result is not None
        assert result["summary_status"] == SummaryStatus.GENERATED
        assert not (tmp_path / "llm_share_card.json").exists()
        errors = _error_messages(mock_logger)
        matched = [
            m for m in errors if "t-f2" in m and "card_generated=True" in m
        ]
        assert matched, (
            f"expected error log with task_id and card_generated, got: {errors}"
        )

    def test_not_requested_preserves_card(self, monkeypatch, tmp_path):
        """A round that did not request the summary (layer already exists)
        must leave the card file untouched."""
        _write_card(tmp_path, {"version": 1, "headline": "untouched", "points": ["p"]})
        _patch_cm(
            monkeypatch,
            tmp_path,
            snapshot={"file_path": str(tmp_path), "llm_summary": "cached summary"},
        )

        llm_ops._save_llm_results(
            task_id="t-skip",
            platform="youtube",
            media_id="m1",
            use_speaker_recognition=False,
            result_dict=_base_result(summary_status=None, share_card=None),
            calibrate_only=False,
            processing_options=normalize_processing_options(
                {"calibrate": True, "summarize": False}
            ),
        )

        card = json.loads(
            (tmp_path / "llm_share_card.json").read_bytes().decode("utf-8")
        )
        assert card["headline"] == "untouched"


class TestShareCardBuildResultDictPassthrough:
    """Coordinator shape -> _build_result_dict -> _save_llm_results."""

    def test_build_result_dict_copies_share_card_and_error(self):
        coordinator = _coordinator_result(
            share_card=dict(VALID_CARD),
            share_card_error="RuntimeError: boom",
        )
        result = llm_ops._build_result_dict(coordinator)
        assert result.get("share_card") == VALID_CARD
        assert result.get("share_card_error") == "RuntimeError: boom"

        omitted = dict(coordinator)
        omitted.pop("share_card")
        omitted.pop("share_card_error")
        without = llm_ops._build_result_dict(omitted)
        assert "share_card" not in without
        assert "share_card_error" not in without

    def test_build_then_save_writes_share_card_file(self, monkeypatch, tmp_path):
        coordinator = _coordinator_result(share_card=dict(VALID_CARD))
        result_dict = llm_ops._build_result_dict(coordinator)
        _run_save(monkeypatch, tmp_path, result_dict)

        card_file = tmp_path / "llm_share_card.json"
        assert card_file.exists()
        card = json.loads(card_file.read_bytes().decode("utf-8"))
        assert card["headline"] == VALID_CARD["headline"]
        assert card["points"] == VALID_CARD["points"]
