import json
import pytest
from src.video_transcript_api.cache.cache_manager import CacheManager
from src.video_transcript_api.utils.llm_status import ChaptersStatus

TERMINAL_STATUSES = [
    ChaptersStatus.GENERATED,
    ChaptersStatus.SKIPPED_SHORT,
    ChaptersStatus.SKIPPED_NO_TIMELINE,
    ChaptersStatus.DISABLED,
]


@pytest.fixture
def cm_and_cache(tmp_path):
    cache_dir = tmp_path / "cache"
    cm = CacheManager(cache_dir=str(cache_dir))
    cm.save_cache(
        platform="youtube", url="https://example.com/v1", media_id="v1",
        use_speaker_recognition=False, transcript_data="Sample",
        transcript_type="capswriter", title="T", author="A", description="D",
    )
    yield cm, cache_dir
    cm.close()


def _read_status(cache_dir):
    return json.loads((list(cache_dir.rglob("llm_status.json"))[0]).read_text(encoding="utf-8"))


@pytest.mark.parametrize("status", TERMINAL_STATUSES)
@pytest.mark.parametrize("mistaken_err", [None, "mistaken error"])
def test_normal_terminal_statuses_clear_stale_chapters_error(cm_and_cache, status, mistaken_err):
    cm, cache_dir = cm_and_cache
    cm.save_llm_status(platform="youtube", media_id="v1", use_speaker_recognition=False,
                       chapters_status="failed", chapters_error="Old failure")
    kwargs = {"chapters_error": mistaken_err} if mistaken_err else {}
    cm.save_llm_status(platform="youtube", media_id="v1", use_speaker_recognition=False,
                       chapters_status=status, **kwargs)
    data = _read_status(cache_dir)
    assert data["chapters_status"] == status
    assert "chapters_error" not in data


@pytest.mark.parametrize("kwargs,expected_status", [
    ({"chapters_status": ChaptersStatus.PENDING}, "pending"),
    ({"chapters_status": ChaptersStatus.FAILED}, "failed"),
    ({"summary_status": "generated"}, "failed"),
])
def test_pending_failed_and_untouched_preserve_stale_error(cm_and_cache, kwargs, expected_status):
    cm, cache_dir = cm_and_cache
    cm.save_llm_status(platform="youtube", media_id="v1", use_speaker_recognition=False,
                       chapters_status="failed", chapters_error="Old failure")
    cm.save_llm_status(platform="youtube", media_id="v1", use_speaker_recognition=False, **kwargs)
    data = _read_status(cache_dir)
    assert data["chapters_status"] == expected_status
    assert data["chapters_error"] == "Old failure"


def test_failed_allows_updating_to_new_error(cm_and_cache):
    cm, cache_dir = cm_and_cache
    cm.save_llm_status(platform="youtube", media_id="v1", use_speaker_recognition=False,
                       chapters_status="failed", chapters_error="Old failure")
    cm.save_llm_status(platform="youtube", media_id="v1", use_speaker_recognition=False,
                       chapters_status="failed", chapters_error="New failure")
    data = _read_status(cache_dir)
    assert data["chapters_status"] == "failed"
    assert data["chapters_error"] == "New failure"
