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
import wave
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from jinja2 import Environment, FileSystemLoader, select_autoescape
from loguru import logger as loguru_logger

import video_transcript_api.api.services.transcription as transcription
from src.video_transcript_api.api.services.view_token_resolver import (
    ViewTokenResolver,
    build_stage_progress_display,
)
from src.video_transcript_api.cache.cache_manager import CacheManager
from src.video_transcript_api.downloaders.models import DownloadInfo, VideoMetadata
from src.video_transcript_api.utils.task_status import TaskStatus
from src.video_transcript_api.utils.perf_tracker import PerfTracker
from src.video_transcript_api.utils.tempfile_manager import TempFileManager

TEMPLATE_DIR = (
    Path(__file__).resolve().parents[2] / "src" / "web" / "templates"
)


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
        with tracked_tracker.track("llm_processing", publish_as="llm"):
            pass

        assert sink.last["stage"] == "llm"
        assert tracked_tracker.get_elapsed("llm_processing") is not None

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
        assert row[0] is not None
        document = json.loads(row[0])
        assert document["stage"] == "download"
        assert document["stage_state"] == "running"


class TestViewStageProgress:
    """The processing view carries the stage progress to the page."""

    @pytest.fixture
    def cm(self, tmp_path):
        manager = CacheManager(cache_dir=str(tmp_path / "cache"))
        yield manager
        manager.close()

    def _publish_running_stage(self, cm, task_id, stage):
        tracker = PerfTracker(task_id=task_id)
        tracker.attach_progress_sink(cm.stage_progress_sink(task_id))
        context = tracker.track(stage)
        context.__enter__()
        return tracker, context

    def test_view_data_contains_running_stage_from_real_entry(self, cm):
        task = cm.create_task(url="https://example.com/view-running")
        tracker, context = self._publish_running_stage(
            cm, task["task_id"], "download"
        )
        try:
            view_data = ViewTokenResolver(cm).get_view_data_by_token(
                task["view_token"]
            )
        finally:
            context.__exit__(None, None, None)

        assert view_data["status"] == "processing"
        display = view_data["stage_progress"]
        assert display is not None
        assert "下载" in display["current_line"]
        assert "已进行" in display["current_line"]
        assert display["completed_items"] == []

    def test_view_data_lists_completed_stages_after_exit(self, cm):
        task = cm.create_task(url="https://example.com/view-completed")
        tracker = PerfTracker(task_id=task["task_id"])
        tracker.attach_progress_sink(cm.stage_progress_sink(task["task_id"]))
        with tracker.track("download"):
            pass
        with tracker.track("transcription"):
            pass

        view_data = ViewTokenResolver(cm).get_view_data_by_token(task["view_token"])
        display = view_data["stage_progress"]
        assert any("下载" in item for item in display["completed_items"])
        assert any("转录" in item for item in display["completed_items"])
        assert any("耗时" in item for item in display["completed_items"])

    def test_view_data_carries_notes_done_total(self, cm):
        """Notes keeps its own detail-write producer; the view must read it.

        The real producer for the notes contract is
        CacheManager.update_task_progress (called by the notes worker);
        the view resolver has to surface done/total unchanged.
        """
        task = cm.create_task(url="https://example.com/view-notes")
        assert cm.update_task_progress(
            task["task_id"], {"stage": "notes", "done": 2, "total": 5}
        ) is True

        view_data = ViewTokenResolver(cm).get_view_data_by_token(task["view_token"])
        display = view_data["stage_progress"]
        assert display["notes_line"] is not None
        assert "2/5" in display["notes_line"]
        assert "详细笔记" in display["current_line"]

    def test_new_stage_without_catalog_entry_still_renders(self, cm):
        """A stage added later via the same entry surfaces by internal name."""
        task = cm.create_task(url="https://example.com/view-new-stage")
        tracker = PerfTracker(task_id=task["task_id"])
        tracker.attach_progress_sink(cm.stage_progress_sink(task["task_id"]))
        with tracker.track("download"):
            pass
        with tracker.track("brand_new_stage"):
            pass

        view_data = ViewTokenResolver(cm).get_view_data_by_token(task["view_token"])
        display = view_data["stage_progress"]
        assert any(
            "brand_new_stage" in item for item in display["completed_items"]
        )

    def test_view_data_without_progress_has_no_stage_display(self, cm):
        task = cm.create_task(url="https://example.com/view-plain")
        view_data = ViewTokenResolver(cm).get_view_data_by_token(task["view_token"])

        assert view_data["status"] == "processing"
        assert view_data["stage_progress"] is None

    def test_terminal_task_view_has_no_stage_progress(self, cm):
        """Lifecycle state wins: a failed task renders the failure page."""
        task = cm.create_task(url="https://example.com/view-terminal")
        tracker = PerfTracker(task_id=task["task_id"])
        tracker.attach_progress_sink(cm.stage_progress_sink(task["task_id"]))
        with tracker.track("download"):
            pass
        assert cm.update_task_status(
            task["task_id"], TaskStatus.FAILED, error_message="boom"
        ) is True

        view_data = ViewTokenResolver(cm).get_view_data_by_token(task["view_token"])
        assert view_data["status"] == "failed"
        assert "stage_progress" not in view_data

    def test_processing_page_renders_stage_progress_html(self, cm):
        task = cm.create_task(url="https://example.com/view-render")
        tracker, context = self._publish_running_stage(
            cm, task["task_id"], "download"
        )
        try:
            view_data = ViewTokenResolver(cm).get_view_data_by_token(
                task["view_token"]
            )
        finally:
            context.__exit__(None, None, None)

        environment = Environment(
            loader=FileSystemLoader(TEMPLATE_DIR),
            autoescape=select_autoescape(["html"]),
        )
        environment.globals["asset_v"] = "unit-test"
        html = environment.get_template("processing.html").render(
            request=None,
            page_title="unit test",
            **view_data,
        )

        assert "当前阶段" in html
        assert "下载" in html
        assert "stage-progress" in html

    def test_display_builder_rejects_malformed_progress(self):
        assert build_stage_progress_display(None) is None
        assert build_stage_progress_display({}) is None
        assert build_stage_progress_display({"stage_state": "running"}) is None


class _RecordingQueue(list):
    """LLM queue double matching the ``put`` interface the handoff uses."""

    def put(self, item):
        self.append(item)


class _StubDownloader:
    """Downloader double: only the external fetches are stubbed.

    ``download_file`` lands a real WAV file and, while the production
    ``tracker.track("download")`` boundary is still open, reads
    ``task_status.progress`` through its own sqlite connection to prove
    the running stage is visible to another reader mid-download.
    """

    use_api_server = False

    def __init__(self, temp_manager, cache_db_path, observations):
        self._temp_manager = temp_manager
        self._cache_db_path = cache_db_path
        self.observations = observations

    def get_metadata(self, url):
        return VideoMetadata(
            video_id="stagee2e",
            platform="youtube",
            title="stage progress e2e",
            author="e2e author",
            description="",
        )

    def get_download_info(self, url):
        return DownloadInfo(
            download_url="http://example.invalid/stagee2e.mp4",
            file_ext="mp4",
            filename="stagee2e.wav",
            downloaded=False,
            local_file=None,
        )

    def get_subtitle(self, url):
        return None

    def download_file(self, url, filename):
        target = Path(self._temp_manager.get_current_task_dir()) / filename
        with wave.open(str(target), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(8000)
            handle.writeframes(b"\x00\x00" * 8000)
        self.observations["download"] = self._read_progress()
        return str(target)

    def _read_progress(self):
        with sqlite3.connect(str(self._cache_db_path)) as reader:
            row = reader.execute(
                "SELECT progress FROM task_status WHERE task_id = ?",
                (self._task_id,),
            ).fetchone()
        return json.loads(row[0]) if row and row[0] else None

    def bind_task(self, task_id):
        self._task_id = task_id


class _StubTranscriber:
    """CapsWriter double: asserts inside the production transcription
    boundary that download already completed and transcription is running."""

    def __init__(self, cache_db_path, task_id, observations):
        self._cache_db_path = cache_db_path
        self._task_id = task_id
        self.observations = observations

    def transcribe(self, local_file, output_base=None, **kwargs):
        with sqlite3.connect(str(self._cache_db_path)) as reader:
            row = reader.execute(
                "SELECT progress FROM task_status WHERE task_id = ?",
                (self._task_id,),
            ).fetchone()
        document = json.loads(row[0]) if row and row[0] else None
        assert document is not None, "no progress row while transcribing"
        assert document["stage"] == "transcription"
        assert document["stage_state"] == "running"
        stage_states = {r["stage"]: r["state"] for r in document["stages"]}
        assert stage_states.get("download") == "done"
        self.observations["transcription"] = document
        return {"transcript": "stub transcript text"}


class TestProcessTranscriptionStagePublishing:
    """E2E: the production entry publishes stage progress end to end."""

    @pytest.fixture
    def pipeline(self, tmp_path, monkeypatch):
        cache = CacheManager(cache_dir=str(tmp_path / "cache"))
        temp_manager = TempFileManager(str(tmp_path / "temp"), retention_hours=24)
        llm_queue = _RecordingQueue()
        router = MagicMock()
        router.notify_task_status.return_value = {"wechat": True}
        monkeypatch.setattr(transcription, "cache_manager", cache)
        monkeypatch.setattr(transcription, "get_temp_manager", lambda: temp_manager)
        monkeypatch.setattr(
            transcription, "get_notification_router", lambda: router
        )
        monkeypatch.setattr(transcription, "llm_task_queue", llm_queue)
        observations = {}
        yield {
            "cache": cache,
            "queue": llm_queue,
            "router": router,
            "temp_manager": temp_manager,
            "observations": observations,
        }
        cache.close()

    def test_stages_publish_from_production_entry_and_reach_the_view(
        self, pipeline, monkeypatch
    ):
        cache = pipeline["cache"]
        url = "https://www.youtube.com/watch?v=stagee2e"
        task = cache.create_task(url=url)
        task_id = task["task_id"]

        downloader = _StubDownloader(
            pipeline["temp_manager"], cache.db_path, pipeline["observations"]
        )
        downloader.bind_task(task_id)
        monkeypatch.setattr(transcription, "create_downloader", lambda u: downloader)
        monkeypatch.setattr(
            transcription,
            "Transcriber",
            lambda: _StubTranscriber(
                cache.db_path, task_id, pipeline["observations"]
            ),
        )

        result = transcription.process_transcription(
            task_id=task_id,
            url=url,
            use_speaker_recognition=False,
        )

        assert result["status"] == "success", result
        assert len(pipeline["queue"]) == 1

        # Mid-download and mid-transcription snapshots were taken through a
        # second sqlite connection inside the stubbed external calls.
        download_doc = pipeline["observations"]["download"]
        assert download_doc["stage"] == "download"
        assert download_doc["stage_state"] == "running"
        transcription_doc = pipeline["observations"]["transcription"]
        assert transcription_doc["stage"] == "transcription"
        assert transcription_doc["stage_state"] == "running"

        # After the run: transcription done, download recorded with elapsed.
        final_doc = cache.get_task_by_id(task_id)["progress"]
        assert final_doc["stage"] == "transcription"
        assert final_doc["stage_state"] == "done"
        final_stage_states = {
            r["stage"]: r["state"] for r in final_doc["stages"]
        }
        assert final_stage_states.get("download") == "done"
        assert final_stage_states.get("transcription") == "done"

        # The view page payload carries the stage display built from the
        # published document.
        view_data = ViewTokenResolver(cache).get_view_data_by_token(
            task["view_token"]
        )
        assert view_data["status"] == "processing"
        display = view_data["stage_progress"]
        assert display is not None
        assert "转录" in display["current_line"]
        assert any("下载" in item for item in display["completed_items"])

        environment = Environment(
            loader=FileSystemLoader(TEMPLATE_DIR),
            autoescape=select_autoescape(["html"]),
        )
        environment.globals["asset_v"] = "unit-test"
        html = environment.get_template("processing.html").render(
            request=None,
            page_title="e2e",
            **view_data,
        )
        assert "当前阶段" in html
        assert "下载" in html
