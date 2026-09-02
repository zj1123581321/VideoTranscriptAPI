"""Unit tests for MediaResolverClient (T1).

Covers HTTP/response -> exception mapping per the Error & Rescue Registry.
All console output is English only.
"""

import base64
import logging

import pytest
import requests

from video_transcript_api.downloaders.media_resolver_client import MediaResolverClient
from video_transcript_api.errors import (
    NetworkError,
    ResolverAuthError,
    ResolverServerError,
    InvalidURLError,
    NonVideoContentError,
    ResolverResolveError,
    ResolverResponseError,
)


class FakeResponse:
    """Minimal stand-in for requests.Response."""

    def __init__(self, status_code=200, json_data=None, text="", raise_json=False):
        self.status_code = status_code
        self._json_data = json_data
        self.text = text or (str(json_data) if json_data is not None else "")
        self._raise_json = raise_json

    def json(self):
        if self._raise_json:
            raise ValueError("no json")
        return self._json_data


def make_client(**kwargs):
    defaults = dict(base_url="http://resolver:8000", api_key="k", max_retries=2, retry_delay=0)
    defaults.update(kwargs)
    return MediaResolverClient(**defaults)


def patch_post(monkeypatch, *responses_or_exc):
    """Patch requests.post to yield given responses/exceptions in sequence."""
    seq = list(responses_or_exc)
    calls = {"n": 0}

    def fake_post(url, json=None, headers=None, timeout=None):
        idx = min(calls["n"], len(seq) - 1)
        calls["n"] += 1
        item = seq[idx]
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(requests, "post", fake_post)
    return calls


# --------------------------------------------------------------------------- #
# construction
# --------------------------------------------------------------------------- #

class TestConstruction:
    def test_requires_base_url(self):
        with pytest.raises(ValueError):
            MediaResolverClient(base_url="", api_key="k")

    def test_requires_api_key(self):
        with pytest.raises(ValueError):
            MediaResolverClient(base_url="http://x", api_key="")

    def test_endpoint_strips_trailing_slash(self):
        c = MediaResolverClient(base_url="http://x:8000/", api_key="k")
        assert c.resolve_endpoint == "http://x:8000/api/resolve"


# --------------------------------------------------------------------------- #
# success
# --------------------------------------------------------------------------- #

class TestSuccess:
    def test_returns_data_on_success(self, monkeypatch):
        data = {"platform": "douyin", "video_id": "1", "video_url": "http://cdn/v.mp4"}
        patch_post(monkeypatch, FakeResponse(200, {"success": True, "data": data}))
        out = make_client().resolve("http://v.douyin.com/abc")
        assert out["video_url"] == "http://cdn/v.mp4"

    def test_sends_api_key_and_payload(self, monkeypatch):
        captured = {}

        def fake_post(url, json=None, headers=None, timeout=None):
            captured["url"] = url
            captured["json"] = json
            captured["headers"] = headers
            return FakeResponse(200, {"success": True, "data": {"video_url": "http://x/v.mp4"}})

        monkeypatch.setattr(requests, "post", fake_post)
        make_client().resolve("http://page", force_refresh=True)
        assert captured["url"].endswith("/api/resolve")
        assert captured["headers"]["X-API-Key"] == "k"
        assert captured["json"] == {"url": "http://page", "translate": False, "force_refresh": True}


# --------------------------------------------------------------------------- #
# HTTP-layer errors
# --------------------------------------------------------------------------- #

class TestHttpErrors:
    def test_401_auth(self, monkeypatch):
        patch_post(monkeypatch, FakeResponse(401, text="unauthorized"))
        with pytest.raises(ResolverAuthError):
            make_client().resolve("http://page")

    def test_400_invalid_url(self, monkeypatch):
        patch_post(monkeypatch, FakeResponse(400, text="bad url"))
        with pytest.raises(InvalidURLError):
            make_client().resolve("http://page")

    def test_500_retries_then_server_error(self, monkeypatch):
        calls = patch_post(monkeypatch, FakeResponse(500, text="boom"), FakeResponse(500, text="boom"))
        with pytest.raises(ResolverServerError):
            make_client(max_retries=2).resolve("http://page")
        assert calls["n"] == 2  # retried

    def test_500_then_success_recovers(self, monkeypatch):
        patch_post(
            monkeypatch,
            FakeResponse(500, text="boom"),
            FakeResponse(200, {"success": True, "data": {"video_url": "http://x/v.mp4"}}),
        )
        out = make_client(max_retries=2).resolve("http://page")
        assert out["video_url"] == "http://x/v.mp4"

    def test_unexpected_status_is_response_error(self, monkeypatch):
        patch_post(monkeypatch, FakeResponse(404, text="nope"))
        with pytest.raises(ResolverResponseError):
            make_client().resolve("http://page")


# --------------------------------------------------------------------------- #
# network errors
# --------------------------------------------------------------------------- #

class TestNetworkErrors:
    def test_timeout_retries_then_network_error(self, monkeypatch):
        calls = patch_post(
            monkeypatch,
            requests.exceptions.Timeout("t"),
            requests.exceptions.Timeout("t"),
        )
        with pytest.raises(NetworkError):
            make_client(max_retries=2).resolve("http://page")
        assert calls["n"] == 2

    def test_connection_error_recovers(self, monkeypatch):
        patch_post(
            monkeypatch,
            requests.exceptions.ConnectionError("refused"),
            FakeResponse(200, {"success": True, "data": {"video_url": "http://x/v.mp4"}}),
        )
        out = make_client(max_retries=2).resolve("http://page")
        assert out["video_url"] == "http://x/v.mp4"


# --------------------------------------------------------------------------- #
# success=false classification (T8 contract)
# --------------------------------------------------------------------------- #

class TestFailureClassification:
    @pytest.mark.parametrize("code", ["NON_VIDEO_CONTENT", "IMAGE_TEXT", "DELETED", "PRIVATE"])
    def test_terminal_codes_non_video(self, monkeypatch, code):
        patch_post(monkeypatch, FakeResponse(200, {"success": False, "error": {"code": code, "message": "x"}}))
        with pytest.raises(NonVideoContentError):
            make_client().resolve("http://page")

    @pytest.mark.parametrize("code", ["ALL_SOURCES_FAILED", "RESOLVE_FAILED"])
    def test_all_source_fail_codes(self, monkeypatch, code):
        patch_post(monkeypatch, FakeResponse(200, {"success": False, "error": {"code": code, "message": "x"}}))
        with pytest.raises(ResolverResolveError):
            make_client().resolve("http://page")

    def test_text_fallback_non_video(self, monkeypatch):
        # no code, message indicates image-text post
        patch_post(monkeypatch, FakeResponse(200, {"success": False, "error": {"message": "该内容为图文笔记"}}))
        with pytest.raises(NonVideoContentError):
            make_client().resolve("http://page")

    def test_unknown_failure_defaults_resolve_error(self, monkeypatch):
        patch_post(monkeypatch, FakeResponse(200, {"success": False, "error": {"message": "weird"}}))
        with pytest.raises(ResolverResolveError):
            make_client().resolve("http://page")

    def test_error_as_plain_string(self, monkeypatch):
        patch_post(monkeypatch, FakeResponse(200, {"success": False, "error": "deleted"}))
        with pytest.raises(NonVideoContentError):
            make_client().resolve("http://page")


# --------------------------------------------------------------------------- #
# malformed responses
# --------------------------------------------------------------------------- #

class TestMalformed:
    def test_non_json_body(self, monkeypatch):
        patch_post(monkeypatch, FakeResponse(200, raise_json=True, text="<html>"))
        with pytest.raises(ResolverResponseError):
            make_client().resolve("http://page")

    def test_success_missing_video_url(self, monkeypatch):
        patch_post(monkeypatch, FakeResponse(200, {"success": True, "data": {"platform": "douyin"}}))
        with pytest.raises(ResolverResponseError):
            make_client().resolve("http://page")

    def test_top_level_not_object(self, monkeypatch):
        patch_post(monkeypatch, FakeResponse(200, ["a", "b"]))
        with pytest.raises(ResolverResponseError):
            make_client().resolve("http://page")


# --------------------------------------------------------------------------- #
# GET /direct (wechat channels plaintext head + CDN URL)
# --------------------------------------------------------------------------- #


_SECRET_CDN = "https://finder.video.qq.com/secret-token-ABCDEF123456.mp4"
_SPH = "AHaM8SrlXX"
_DIRECT_HEAD = b"\x00\x00\x00\x20" + b"ftyp" + b"\x00" * 24


def _direct_payload(**overrides):
    body = {
        "sph_code": _SPH,
        "cdn_url": _SECRET_CDN,
        "content_length": 1000,
        "encrypted_head_bytes": len(_DIRECT_HEAD),
        "head_b64": base64.b64encode(_DIRECT_HEAD).decode("ascii"),
    }
    body.update(overrides)
    return body


def patch_get(monkeypatch, *responses_or_exc):
    seq = list(responses_or_exc)
    calls = {"n": 0, "urls": [], "headers": []}

    def fake_get(url, headers=None, timeout=None, **kwargs):
        calls["urls"].append(url)
        calls["headers"].append(headers)
        idx = min(calls["n"], len(seq) - 1)
        calls["n"] += 1
        item = seq[idx]
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(requests, "get", fake_get)
    return calls


class TestFetchWechatDirect:
    def test_returns_flat_json_and_omits_cdn_from_logs(self, monkeypatch, caplog):
        caplog.set_level(logging.DEBUG)
        calls = patch_get(monkeypatch, FakeResponse(200, _direct_payload()))
        out = make_client().fetch_wechat_direct(_SPH)
        assert out["cdn_url"] == _SECRET_CDN
        assert calls["urls"][0].endswith(f"/api/stream/wechat_channels/{_SPH}/direct")
        assert calls["headers"][0]["X-API-Key"] == "k"
        joined = " ".join(r.getMessage() for r in caplog.records)
        assert _SECRET_CDN not in joined

    def test_401_auth(self, monkeypatch):
        patch_get(monkeypatch, FakeResponse(401, text="unauthorized"))
        with pytest.raises(ResolverAuthError) as ei:
            make_client().fetch_wechat_direct(_SPH)
        assert _SECRET_CDN not in str(ei.value)

    def test_502_retries_then_server_error(self, monkeypatch):
        calls = patch_get(monkeypatch, FakeResponse(502, text="up"), FakeResponse(502, text="up"))
        with pytest.raises(ResolverServerError):
            make_client(max_retries=2).fetch_wechat_direct(_SPH)
        assert calls["n"] == 2

    def test_head_b64_length_mismatch(self, monkeypatch):
        patch_get(monkeypatch, FakeResponse(200, _direct_payload(encrypted_head_bytes=8)))
        with pytest.raises(ResolverResponseError) as ei:
            make_client().fetch_wechat_direct(_SPH)
        assert _SECRET_CDN not in str(ei.value)
