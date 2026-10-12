"""Regression tests for #204: intake failures must not short-circuit resource release.

不变式轴（docs/sessions/261012-issue-fixes/design.md）：
1. 错误记录 writer 抛异常、其余清理成功 → slot/inflight/预算/目录全部释放，HTTP 500 可见。
2. 目录清理失败、未移交 → slot/inflight 释放；目录与已占用预算真实保留，不假报回收。
3. 正常受理（transferred=True）→ handler 不删媒体、不误清预算，worker 持有并释放。
4. receiver acquire 失败 → 不释放未持有的槽（由既有
   tests/integration/test_upload_intake.py::test_receiver_and_inflight_limits_reject_without_body_consumption 覆盖）。
"""

import sqlite3
from pathlib import Path

from tests.integration.test_upload_intake import (  # noqa: F401  fixture re-export
    PRODUCER_METADATA,
    RAW_PRODUCER_BYTES,
    _key,
    _post,
    _wait_for_worker_release,
    upload_client,
)


def test_writer_failure_still_releases_slot_inflight_budget_and_dir(
    upload_client, monkeypatch
):
    """不变式行1：错误记录抛OperationalError、清理成功 → 四项全释放，HTTP 500可见。"""
    client, runtime, body_reads, worker_calls, worker_results = upload_client
    monkeypatch.setenv("VTA_UPLOADS_ENABLED", "true")
    writer_calls = []

    def failing_writer(upload_id, error_code):
        writer_calls.append((upload_id, error_code))
        raise sqlite3.OperationalError("injected writer failure")

    monkeypatch.setattr(runtime.cache_manager, "set_local_upload_error", failing_writer)
    declared = {**PRODUCER_METADATA, "byte_size": len(RAW_PRODUCER_BYTES) + 1}
    key = _key()
    response = _post(client, key, declared, RAW_PRODUCER_BYTES, "writer-failure")

    assert response.status_code == 500, "注入故障必须以HTTP 500可见，不得静默成功"
    assert len(writer_calls) == 1, "注入必须真实命中finally内的错误记录writer"
    assert writer_calls[0][1] == "declared_size_mismatch", "坏body必须先走到declared_size_mismatch"
    record = runtime.cache_manager.get_local_upload_by_owner_key("alice", key)
    assert record["root_task_id"] is None, "失败请求不得产生受理行"
    assert not list(Path(runtime.temp_manager.base_dir).glob("task_*/upload-source.bin")), \
        "接收目录必须已被清理"
    assert runtime.inflight_registry.size("transcription") == 0, "未移交inflight必须已释放"
    assert runtime._upload_reserved_bytes == {}, "临时预算必须归零"
    assert runtime.upload_receiver_slots.acquire(blocking=False), "请求槽必须已释放"
    runtime.upload_receiver_slots.release()

    followup = _post(
        client, _key(), PRODUCER_METADATA, RAW_PRODUCER_BYTES, "after-writer-failure"
    )
    assert followup.status_code == 202, "后继上传不得因槽泄漏而503"
    assert followup.json()["state"] == "accepted"
    worker_results.get(timeout=2)
    _wait_for_worker_release(runtime)


def test_directory_cleanup_failure_releases_slot_inflight_and_keeps_budget_honest(
    upload_client, monkeypatch
):
    """不变式行2：目录清理失败、未移交 → slot/inflight释放；目录与预算真实保留。"""
    client, runtime, body_reads, worker_calls, _worker_results = upload_client
    monkeypatch.setenv("VTA_UPLOADS_ENABLED", "true")
    cleanup_calls = []

    def stalled_cleanup(task_id):
        cleanup_calls.append(task_id)
        return 0  # 受控IO故障：目录留在盘上不清理

    monkeypatch.setattr(runtime.temp_manager, "clean_up_task", stalled_cleanup)
    declared = {**PRODUCER_METADATA, "byte_size": len(RAW_PRODUCER_BYTES) + 1}
    key = _key()
    response = _post(client, key, declared, RAW_PRODUCER_BYTES, "cleanup-failure")

    assert response.status_code == 500, "清理失败必须以HTTP 500可见，不得静默成功"
    assert len(cleanup_calls) == 1, "注入必须真实命中目录清理"
    record = runtime.cache_manager.get_local_upload_by_owner_key("alice", key)
    assert record["error_code"] == "declared_size_mismatch", "错误记录先于清理，必须仍可见"
    assert record["root_task_id"] is None
    media_path = Path(record["media_path"])
    assert media_path.exists(), "目录清理失败时媒体文件必须真实仍在"
    assert list(runtime._upload_reserved_bytes.values()) == [declared["byte_size"]], \
        "目录仍占盘，预算不得假报已回收"
    assert runtime.inflight_registry.size("transcription") == 0, "未移交inflight必须已释放"
    assert runtime.upload_receiver_slots.acquire(blocking=False), "请求槽必须已释放"
    runtime.upload_receiver_slots.release()


def test_accepted_transfer_keeps_media_ownership_with_worker(upload_client, monkeypatch):
    """不变式行3：受理移交后handler不删媒体、不误清预算，worker真实持有并释放。"""
    client, runtime, body_reads, worker_calls, worker_results = upload_client
    monkeypatch.setenv("VTA_UPLOADS_ENABLED", "true")
    key = _key()
    response = _post(client, key, PRODUCER_METADATA, RAW_PRODUCER_BYTES, "accepted-transfer")

    assert response.status_code == 202
    receipt = response.json()
    assert receipt["state"] == "accepted"
    stored = runtime.cache_manager.get_local_upload_by_owner_key("alice", key)
    assert stored["state"] == "accepted"
    assert stored["root_task_id"] == receipt["task_id"]
    assert Path(stored["media_path"]).read_bytes() == RAW_PRODUCER_BYTES, \
        "移交后handler不得删除或改写媒体"
    dispatched = worker_results.get(timeout=2)
    assert dispatched["task_id"] == receipt["task_id"]
    assert dispatched["bytes"] == RAW_PRODUCER_BYTES, "worker必须拿到真实媒体字节"
    _wait_for_worker_release(runtime)
    assert runtime.task_queue.qsize() == 0
