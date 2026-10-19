"""Unified stage-entry publishing for ``task_status.progress``.

Locks the contract of the single stage boundary (``PerfTracker.track``):
entering a stage publishes the running document, exiting publishes done
with the elapsed interval, an exception publishes failed plus the
grep-able ``stage_progress_failed`` log line, sub-progress (notes
done/total) rides on the current stage document, and a completed stage
never leaves a running stage behind. Persistence-level behavior (the
terminal-state guard and the second-connection visibility) is locked in
the CacheManager test classes below.

All console output must be in English only (no emoji, no Chinese).
"""

import datetime
import json
import sqlite3

import pytest
from loguru import logger as loguru_logger

from src.video_transcript_api.cache.cache_manager import CacheManager
from src.video_transcript_api.utils.task_status import TaskStatus
from src.video_transcript_api.utils.perf_tracker import PerfTracker


class RecordingSink:
    """Collect every published progress document in order."""

    def __init__(self):
        self.documents = []

    def __call__(self, document):
        self.documents.append(document)
        return True

    @property
    def last(self):
        assert self.documents, "no progress document was published"
        return self.documents[-1]


@pytest.fixture
def sink():
    return RecordingSink()


@pytest.fixture
def tracked_tracker(sink):
    tracker = PerfTracker(task_id="task-stage")
    tracker.attach_progress_sink(sink)
    return tracker


class TestStageEntryPublishing:
    """The track() boundary is the only stage-progress publisher."""

    def test_stage_enter_is_visible_to_another_reader(self, tracked_tracker, sink):
        with tracked_tracker.track("download"):
            document = sink.last

        assert document["stage"] == "download"
        assert document["stage_state"] == "running"
        started_at = datetime.datetime.fromisoformat(document["started_at"])
        assert started_at.tzinfo is not None

    def test_stage_exit_publishes_done_with_elapsed(self, tracked_tracker, sink):
        with tracked_tracker.track("download"):
            pass

        document = sink.last
        assert document["stage"] == "download"
        assert document["stage_state"] == "done"
        assert document["stages"][-1]["stage"] == "download"
        assert document["stages"][-1]["state"] == "done"
        assert document["stages"][-1]["elapsed_ms"] >= 0

    def test_stage_exception_publishes_failed_and_logs_literal(
        self, tracked_tracker, sink
    ):
        captured = []
        handler_id = loguru_logger.add(captured.append, level="ERROR")
        try:
            with pytest.raises(ValueError, match="boom"):
                with tracked_tracker.track("download"):
                    raise ValueError("boom")
        finally:
            loguru_logger.remove(handler_id)

        document = sink.last
        assert document["stage_state"] == "failed"
        assert document["stages"][-1]["state"] == "failed"
        failure_logs = [
            message for message in captured if "stage_progress_failed" in message
        ]
        assert failure_logs, captured

    def test_publish_as_keeps_internal_name_out_of_the_document(
        self, tracked_tracker, sink
    ):
        with tracked_tracker.track("llm_processing", publish_as="notes"):
            pass

        assert sink.last["stage"] == "notes"
        assert tracked_tracker.get_elapsed("llm_processing") is not None

    def test_subprogress_rides_on_current_stage_document(self, tracked_tracker, sink):
        with tracked_tracker.track("llm_processing", publish_as="notes"):
            assert tracked_tracker.report_subprogress(done=2, total=5) is True
            document = sink.last

        assert document["stage"] == "notes"
        assert document["stage_state"] == "running"
        assert document["done"] == 2
        assert document["total"] == 5
        assert "done" not in sink.last

    def test_subprogress_without_running_stage_is_rejected(self, tracked_tracker):
        assert tracked_tracker.report_subprogress(done=0, total=3) is False

    def test_completed_stage_leaves_no_running_state(self, tracked_tracker, sink):
        """Cache-hit style short circuit: the last exit must be terminal."""
        with tracked_tracker.track("url_parse"):
            pass
        with tracked_tracker.track("cache_check"):
            pass

        document = sink.last
        assert document["stage_state"] == "done"
        assert all(
            record["state"] in ("done", "failed")
            for record in document["stages"]
        )
        assert [record["stage"] for record in document["stages"]] == [
            "url_parse",
            "cache_check",
        ]

    def test_missing_sink_keeps_track_purely_in_memory(self):
        tracker = PerfTracker(task_id="task-plain")
        with tracker.track("download"):
            pass

        assert tracker.get_elapsed("download") is not None
        assert tracker.report_subprogress(done=1, total=2) is False


class TestTerminalStateGuard:
    """Late stage writes must never overwrite a terminal task row."""

    @pytest.fixture
    def cm(self, tmp_path):
        manager = CacheManager(cache_dir=str(tmp_path / "cache"))
        yield manager
        manager.close()

    def test_late_write_after_success_is_rejected(self, cm):
        task = cm.create_task(url="https://example.com/late-success")
        assert cm.update_task_status(task["task_id"], TaskStatus.SUCCESS) is True

        assert (
            cm.update_task_progress(
                task["task_id"], {"stage": "download", "stage_state": "running"}
            )
            is False
        )
        assert cm.get_task_by_id(task["task_id"])["progress"] is None

    def test_late_write_after_failed_is_rejected(self, cm):
        task = cm.create_task(url="https://example.com/late-failed")
        assert cm.update_task_status(task["task_id"], TaskStatus.FAILED) is True

        assert (
            cm.update_task_progress(
                task["task_id"], {"stage": "transcription", "stage_state": "running"}
            )
            is False
        )
        assert cm.get_task_by_id(task["task_id"])["progress"] is None

    def test_write_while_processing_is_accepted(self, cm):
        task = cm.create_task(url="https://example.com/running-write")
        progress = {"stage": "download", "stage_state": "running", "started_at": "x"}

        assert cm.update_task_progress(task["task_id"], progress) is True
        assert cm.get_task_by_id(task["task_id"])["progress"] == progress

    def test_stage_progress_visible_from_second_connection(self, cm):
        """The acceptance path: a reader on its own sqlite connection sees
        the running stage written by the unified entry mid-stage."""
        task = cm.create_task(url="https://example.com/second-reader")
        tracker = PerfTracker(task_id=task["task_id"])
        tracker.attach_progress_sink(cm.stage_progress_sink(task["task_id"]))

        with tracker.track("download"):
            with sqlite3.connect(str(cm.db_path)) as reader:
                row = reader.execute(
                    "SELECT progress FROM task_status WHERE task_id = ?",
                    (task["task_id"],),
                ).fetchone()

        assert row is not None
        document = json.loads(row[0])
        assert document["stage"] == "download"
        assert document["stage_state"] == "running"
