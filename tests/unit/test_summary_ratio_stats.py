"""Tests for summary ratio monitoring service."""

import json
from pathlib import Path

import pytest

from video_transcript_api.api.services.summary_ratio_stats import compute_summary_ratio_stats
from video_transcript_api.cache.cache_manager import CacheManager
from video_transcript_api.utils.logging.audit_logger import AuditLogger
from video_transcript_api.utils.llm_status import SummaryStatus


def _seed_task(
    tmp_path: Path,
    *,
    task_id: str,
    media_id: str,
    original_text: str,
    summary_text: str,
    original_length_band: int,
):
  cache_root = tmp_path / "cache"
  audit_path = tmp_path / "audit.db"
  cm = CacheManager(cache_dir=str(cache_root))
  audit = AuditLogger(str(audit_path))

  cm.save_cache(
    platform="youtube",
    url=f"https://www.youtube.com/watch?v={media_id}",
    media_id=media_id,
    use_speaker_recognition=False,
    transcript_data=original_text,
    transcript_type="capswriter",
    title="Title",
    author="Author",
    description="Desc",
  )
  cm.save_llm_result(
    platform="youtube",
    media_id=media_id,
    use_speaker_recognition=False,
    llm_type="summary",
    content=summary_text,
  )
  task = cm.create_task(
    url=f"https://www.youtube.com/watch?v={media_id}",
    use_speaker_recognition=False,
    platform="youtube",
    media_id=media_id,
  )
  created_task_id = task["task_id"]
  cm.update_task_status(created_task_id, "success", summary_status=SummaryStatus.GENERATED)

  audit.archive_task_snapshot(
    {
      "task_id": created_task_id,
      "view_token": task["view_token"],
      "title": "Title",
      "author": "Author",
      "platform": "youtube",
      "status": "success",
      "summary_status": SummaryStatus.GENERATED,
      "submitted_by": "user-1",
      "completed_at": "2026-08-24 12:00:00",
    }
  )

  # Pad original transcript file to target band without changing summary ratio much
  artifact_dir = Path(cm.get_cache("youtube", media_id, False)["file_path"])
  transcript_path = artifact_dir / "transcript_capswriter.txt"
  padded = original_text + ("x" * max(0, original_length_band - len(original_text)))
  transcript_path.write_text(padded, encoding="utf-8")

  audit.close()
  cm.close()
  return created_task_id, cache_root, audit_path


def test_compute_summary_ratio_stats_fixture(tmp_path):
  _seed_task(
    tmp_path,
    task_id="t1",
    media_id="vid-s",
    original_text="original transcript text for ratio",
    summary_text="summary " * 200,
    original_length_band=2000,
  )

  cache_root = tmp_path / "cache"
  audit_path = tmp_path / "audit.db"
  cache_db = cache_root / "cache.db"

  result = compute_summary_ratio_stats(
    audit_db_path=str(audit_path),
    cache_db_path=str(cache_db),
    cache_root=cache_root,
    days=30,
  )

  assert result["bands"]["S"]["n"] == 1
  assert result["bands"]["S"]["median_ratio"] > 0
  assert result["sampled_tasks"] == 1


def test_over_hardcap_counted(tmp_path):
  _seed_task(
    tmp_path,
    task_id="t2",
    media_id="vid-hardcap",
    original_text="short",
    summary_text="x" * 5000,
    original_length_band=2000,
  )

  cache_root = tmp_path / "cache"
  result = compute_summary_ratio_stats(
    audit_db_path=str(tmp_path / "audit.db"),
    cache_db_path=str(cache_root / "cache.db"),
    cache_root=cache_root,
    days=30,
  )
  assert result["bands"]["S"]["over_hardcap"] == 1
