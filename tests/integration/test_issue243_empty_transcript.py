"""Issue #243: empty producer output must not become a successful cache entry."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from capswriter_asr import Transcript
from video_transcript_api.api.services import transcription
from video_transcript_api.cache.cache_manager import CacheManager
from video_transcript_api.downloaders import generic
from video_transcript_api.downloaders.youtube_api_client import YouTubeApiClient
from video_transcript_api.errors import EmptyTranscriptError
from video_transcript_api.transcriber import capswriter_client, transcriber as transcriber_module
from video_transcript_api.transcriber.funasr_client import FunASRSpeakerClient
from video_transcript_api.utils import url_validator


def _process_fixture(
    tmp_path, monkeypatch, *, route, segments=None, api_result=None,
    use_speaker_recognition=True, seed_cache=False,
):
    cache = CacheManager(str(tmp_path / "cache"))
    media_id = f"issue243-{tmp_path.name}"
    url = (
        "https://youtube.com/watch?v=fixture"
        if route == "youtube-api"
        else f"recorder://fixture/{media_id}"
    )
    media = tmp_path / "fixture.mp4"
    media.write_bytes(b"local fixture; external audio work is isolated")
    if seed_cache:
        cache.save_cache(
            platform="youtube", url=url, media_id=media_id,
            use_speaker_recognition=False, transcript_data="previous valid transcript",
            transcript_type="capswriter", title="Existing", author="Fixture",
        )

    task_id = cache.create_task(url=url)["task_id"]
    queue = MagicMock()
    monkeypatch.setattr(transcription, "cache_manager", cache)
    monkeypatch.setattr(transcription, "get_notification_router", lambda: MagicMock())
    monkeypatch.setattr(transcription, "get_inflight_registry", lambda: MagicMock())
    monkeypatch.setattr(transcription, "get_temp_manager", lambda: MagicMock())
    monkeypatch.setattr(transcription, "llm_task_queue", queue)
    monkeypatch.setattr(transcription, "_ensure_audio_track", lambda _path: None)

    if segments is not None:
        client = FunASRSpeakerClient()
        producer_result = client._finalize({"segments": segments, "speakers": []}, 0)
        monkeypatch.setattr(transcription, "FunASRSpeakerClient", lambda: client)
        monkeypatch.setattr(
            client, "transcribe_with_speaker_recognition",
            AsyncMock(return_value=producer_result),
        )

    if route == "youtube-api":
        class YoutubeDownloader:
            use_api_server = True

            def get_metadata(self, _url):
                return SimpleNamespace(
                    video_id=media_id, title="Fixture", author="Fixture",
                    description="", platform="youtube",
                )

            def fetch_for_transcription(self, _url, _use_speaker_recognition):
                return api_result

        monkeypatch.setattr(transcription, "create_downloader", lambda _url: YoutubeDownloader())
    else:
        monkeypatch.setattr(url_validator, "validate_url_safe", lambda value: value)
        monkeypatch.setattr(
            generic.GenericDownloader,
            "download_file",
            lambda *_args, **_kwargs: str(media),
        )

    result = transcription.process_transcription(
        task_id,
        url,
        download_url=None if route == "youtube-api" else "https://example.invalid/audio",
        metadata_override={"title": "Fixture", "author": "Fixture"},
        preparsed_url=SimpleNamespace(
            platform="youtube", video_id=media_id, normalized_url=url, is_short_url=False,
        ),
        processing_options={"calibrate": False, "summarize": False},
        use_speaker_recognition=use_speaker_recognition,
    )
    return cache, task_id, media_id, result, queue


@pytest.mark.parametrize(
    ("route", "segments"),
    [
        ("main", []),
        ("main", [{"text": " \t "}]),
        ("youtube-api", []),
        ("youtube-api", [{"text": " \t "}]),
    ],
    ids=["main-empty", "main-whitespace", "youtube-api-empty", "youtube-api-whitespace"],
)
def test_empty_funasr_fails_before_cache_and_handoff(tmp_path, monkeypatch, route, segments):
    api_result = None
    if route == "youtube-api":
        api_result = {
            "video_id": f"issue243-{tmp_path.name}", "video_title": "Fixture",
            "author": "Fixture", "description": "", "platform": "youtube",
            "need_transcription": True, "audio_path": str(tmp_path / "fixture.mp4"),
        }
    cache, task_id, media_id, result, queue = _process_fixture(
        tmp_path, monkeypatch, route=route, segments=segments, api_result=api_result,
    )

    assert result["status"] == "failed"
    task = cache.get_task_by_id(task_id)
    assert task["status"] == "failed"
    assert "Transcript is empty" in task["error_message"]
    assert cache.get_cache("youtube", media_id, use_speaker_recognition=True) is None
    queue.put.assert_not_called()


@pytest.mark.parametrize("route", ["main", "youtube-api"])
def test_numeric_funasr_transcript_is_cached_and_handed_off(tmp_path, monkeypatch, route):
    api_result = None
    if route == "youtube-api":
        api_result = {
            "video_id": f"issue243-{tmp_path.name}", "video_title": "Fixture",
            "author": "Fixture", "description": "", "platform": "youtube",
            "need_transcription": True, "audio_path": str(tmp_path / "fixture.mp4"),
        }
    cache, task_id, media_id, result, queue = _process_fixture(
        tmp_path, monkeypatch, route=route, segments=[{"text": "123"}], api_result=api_result,
    )

    assert result["status"] == "success"
    assert cache.get_task_by_id(task_id)["status"] == "calibrating"
    cached = cache.get_cache("youtube", media_id, use_speaker_recognition=True)
    assert cached["transcript_data"]["segments"] == [{"text": "123"}]
    assert queue.put.call_args.args[0]["transcript"] == "Unknown：123"


def test_empty_funasr_does_not_mask_existing_valid_cache(tmp_path, monkeypatch):
    cache, _task_id, media_id, result, queue = _process_fixture(
        tmp_path, monkeypatch, route="main", segments=[], seed_cache=True,
    )

    assert result["status"] == "failed"
    existing = cache.get_cache("youtube", media_id, use_speaker_recognition=False)
    assert existing["transcript_data"] == "previous valid transcript"
    assert cache.get_cache("youtube", media_id, use_speaker_recognition=True) is None
    assert not list(Path(tmp_path / "cache").rglob("*_funasr.json"))
    queue.put.assert_not_called()


@pytest.mark.parametrize("srt, expected_text", [("", None), (
    "1\n00:00:01,000 --> 00:00:04,000\n42\n\n2\n00:00:05,000 --> 00:00:08,000\n100\n",
    "42 100",
)], ids=["empty-subtitle", "numeric-structured-subtitle"])
def test_youtube_api_subtitles_require_text_or_preserved_segments(
    tmp_path, monkeypatch, srt, expected_text,
):
    parsed = YouTubeApiClient.parse_srt_to_subtitle_result(srt)
    api_result = {
        "video_id": f"issue243-{tmp_path.name}", "video_title": "Fixture",
        "author": "Fixture", "description": "", "platform": "youtube",
        "need_transcription": False, "transcript": parsed.text,
        "transcript_segments": parsed.segments,
    }
    cache, task_id, media_id, result, queue = _process_fixture(
        tmp_path, monkeypatch, route="youtube-api", api_result=api_result,
        use_speaker_recognition=False,
    )

    if expected_text is None:
        assert result["status"] == "failed"
        assert cache.get_task_by_id(task_id)["status"] == "failed"
        assert cache.get_cache("youtube", media_id, use_speaker_recognition=False) is None
        queue.put.assert_not_called()
    else:
        assert result["status"] == "success"
        assert cache.get_task_by_id(task_id)["status"] == "calibrating"
        cached = cache.get_cache(
            "youtube", media_id, use_speaker_recognition=False,
        )
        assert cached["transcript_data"] == expected_text
        assert queue.put.call_args.args[0]["transcript"] == expected_text


def test_capswriter_whitespace_token_is_rejected_after_real_file_read(tmp_path, monkeypatch):
    output_dir = tmp_path / "capswriter-output"
    audio = tmp_path / "fixture.wav"
    audio.write_bytes(b"local fixture")
    monkeypatch.setattr(transcriber_module, "get_workspace_dir", lambda: str(output_dir))
    monkeypatch.setattr(capswriter_client, "load_config", lambda: {"storage": {}, "capswriter": {}})
    monkeypatch.setattr(capswriter_client.Config, "generate_funasr_compat", False)
    monkeypatch.setattr(
        capswriter_client, "transcribe_file_sync",
        lambda *_args, **_kwargs: Transcript(
            text=" ", tokens=[" "], timestamps=[0.0], duration=1.0,
            raw={"text_accu": " ", "task_id": "issue243-whitespace"},
        ),
    )
    transcriber = transcriber_module.Transcriber(
        config={"capswriter": {"server_url": "ws://localhost:6006"}, "storage": {}},
    )

    with pytest.raises(EmptyTranscriptError, match="Transcript is empty"):
        transcriber.transcribe(str(audio), "whitespace")

    assert (output_dir / "fixture.txt").read_text(encoding="utf-8") == " "
