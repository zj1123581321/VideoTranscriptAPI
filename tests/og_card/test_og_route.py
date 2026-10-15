"""Route tests for GET /og/{view_token}.png.

Wires the real views router against a real CacheManager on tmp_path, with
font paths injected through the web config (fixture subset fonts, never
system fonts). SAMPLE_CARD doubles as the glyph-coverage source for the
font subsets: rerun fonts/build_subsets.py after editing its text.

All console output must be in English only (no emoji, no Chinese).
"""

import json
import os
import time
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from video_transcript_api.api.routes import views as views_routes
from video_transcript_api.cache.cache_manager import CacheManager
from video_transcript_api.utils.rendering import og_card

FONTS_DIR = Path(__file__).parent / "fonts"
REGULAR_FONT = FONTS_DIR / "NotoSansSC-Regular-subset.ttf"
BOLD_FONT = FONTS_DIR / "NotoSansSC-Bold-subset.ttf"

SITE_URL = "https://sum.zlxlabs.com"

SAMPLE_CARD = {
    "version": 1,
    "headline": "DeepSeek-R2 深度实测：推理成本再降一个数量级",
    "points": [
        "官方基准全量复跑，数学与代码成绩逐项核对",
        "开源权重与商用 API 的差距缩小到 5% 以内",
        "附完整评测脚本与可复现的实验环境配置",
    ],
    "generated_at": "2026-10-15T16:00:00+08:00",
}


def _write_card(cache_dir: Path, card) -> Path:
    path = cache_dir / og_card.CARD_FILENAME
    path.write_text(json.dumps(card, ensure_ascii=False), encoding="utf-8")
    return path


@pytest.fixture
def og_client(tmp_path, monkeypatch):
    assert REGULAR_FONT.is_file() and BOLD_FONT.is_file(), (
        "fixture fonts missing; rerun fonts/build_subsets.py"
    )
    cache = CacheManager(str(tmp_path / "cache"))
    task_info = cache.create_task(
        url="https://www.youtube.com/watch?v=abc123",
        platform="youtube",
        media_id="abc123",
    )
    cache.save_cache(
        platform="youtube",
        url="https://www.youtube.com/watch?v=abc123",
        media_id="abc123",
        use_speaker_recognition=False,
        transcript_data="hello transcript body",
        transcript_type="capswriter",
        title="DeepSeek-R2 深度实测",
        author="AI 前沿观察",
        description="demo description",
    )
    cache_data = cache.get_cache(platform="youtube", media_id="abc123")
    cache_dir = Path(cache_data["file_path"])

    monkeypatch.setattr(views_routes, "cache_manager", cache)
    monkeypatch.setattr(
        views_routes,
        "get_config",
        lambda: {
            "web": {
                "og_font_path": str(REGULAR_FONT),
                "og_font_bold_path": str(BOLD_FONT),
            }
        },
    )
    monkeypatch.setattr(views_routes, "get_base_url", lambda: SITE_URL)

    app = FastAPI()
    app.include_router(views_routes.router)
    client = TestClient(app)
    yield client, cache, task_info["view_token"], cache_dir
    client.close()
    cache.close()


def _png_dimensions(body: bytes):
    from io import BytesIO

    from PIL import Image

    with Image.open(BytesIO(body)) as img:
        return img.format, img.size


def _bad_card_overrides() -> dict:
    """Contract violations; each key is one dimension (feedback F1)."""
    return {
        "version-not-1": {"version": 2},
        "headline-empty": {"headline": ""},
        "headline-too-long": {"headline": "标" * 31},
        "points-empty": {"points": []},
        "points-four": {"points": ["一", "二", "三", "四"]},
        "point-empty": {"points": ["ok", ""]},
        "point-too-long": {"points": ["x" * 81]},
        "generated-at-invalid": {"generated_at": "not-a-timestamp"},
    }


class TestOgShareCardRoute:
    def test_serves_1200x630_png(self, og_client):
        client, _cache, token, cache_dir = og_client
        _write_card(cache_dir, SAMPLE_CARD)
        response = client.get(f"/og/{token}.png")
        assert response.status_code == 200
        assert response.headers["content-type"] == "image/png"
        assert (cache_dir / og_card.PNG_FILENAME).is_file()
        fmt, size = _png_dimensions(response.content)
        assert (fmt, size) == ("PNG", (og_card.WIDTH, og_card.HEIGHT))

    def test_second_request_hits_cached_file(self, og_client):
        client, _cache, token, cache_dir = og_client
        _write_card(cache_dir, SAMPLE_CARD)
        assert client.get(f"/og/{token}.png").status_code == 200
        png_path = cache_dir / og_card.PNG_FILENAME
        sentinel = b"cached-sentinel-not-a-png"
        png_path.write_bytes(sentinel)
        json_path = cache_dir / og_card.CARD_FILENAME
        # Keep the cache decision deterministic: cache must be judged fresh.
        old = time.time() - 100
        os.utime(json_path, (old, old))

        response = client.get(f"/og/{token}.png")
        assert response.status_code == 200
        assert response.content == sentinel

    def test_regenerated_card_json_rerenders(self, og_client):
        client, _cache, token, cache_dir = og_client
        json_path = _write_card(cache_dir, SAMPLE_CARD)
        assert client.get(f"/og/{token}.png").status_code == 200
        png_path = cache_dir / og_card.PNG_FILENAME
        png_path.write_bytes(b"stale-sentinel")
        # A regenerated card (e.g. resummarize) is newer than the cached PNG.
        future = time.time() + 100
        os.utime(json_path, (future, future))

        response = client.get(f"/og/{token}.png")
        assert response.status_code == 200
        fmt, size = _png_dimensions(response.content)
        assert (fmt, size) == ("PNG", (og_card.WIDTH, og_card.HEIGHT))

    def test_missing_card_returns_404(self, og_client):
        client, _cache, token, _cache_dir = og_client
        response = client.get(f"/og/{token}.png")
        assert response.status_code == 404

    @pytest.mark.parametrize(
        "case", sorted(_bad_card_overrides()), ids=sorted(_bad_card_overrides())
    )
    def test_invalid_card_returns_404(self, og_client, case):
        client, _cache, token, cache_dir = og_client
        _write_card(cache_dir, {**SAMPLE_CARD, **_bad_card_overrides()[case]})
        assert client.get(f"/og/{token}.png").status_code == 404

    def test_missing_generated_at_returns_404(self, og_client):
        client, _cache, token, cache_dir = og_client
        card = {k: v for k, v in SAMPLE_CARD.items() if k != "generated_at"}
        _write_card(cache_dir, card)
        assert client.get(f"/og/{token}.png").status_code == 404

    def test_cache_control_is_max_age_300(self, og_client):
        client, _cache, token, cache_dir = og_client
        _write_card(cache_dir, SAMPLE_CARD)
        response = client.get(f"/og/{token}.png")
        assert response.headers["cache-control"] == "public, max-age=300"

    def test_json_deleted_in_window_returns_404(self, og_client, monkeypatch):
        """A resummarize deletes the card json between load_share_card and
        the freshness stat: must 404, not leak FileNotFoundError as 500."""
        client, _cache, token, cache_dir = og_client
        _write_card(cache_dir, SAMPLE_CARD)
        assert client.get(f"/og/{token}.png").status_code == 200
        real_load = og_card.load_share_card

        def load_then_delete(cache_dir_):
            card = real_load(cache_dir_)
            (Path(cache_dir_) / og_card.CARD_FILENAME).unlink()
            return card

        monkeypatch.setattr(views_routes, "load_share_card", load_then_delete)
        strict_client = TestClient(client.app, raise_server_exceptions=False)
        response = strict_client.get(f"/og/{token}.png")
        assert response.status_code == 404

    def test_unknown_token_returns_404(self, og_client):
        client, _cache, _token, cache_dir = og_client
        _write_card(cache_dir, SAMPLE_CARD)
        assert client.get("/og/no-such-token.png").status_code == 404

    def test_view_route_still_matches(self, og_client):
        """Route-order guard: /og must not shadow /view and vice versa."""
        client, _cache, token, cache_dir = og_client
        _write_card(cache_dir, SAMPLE_CARD)
        assert client.get(f"/view/{token}").status_code == 200
        assert client.get(f"/og/{token}.png").status_code == 200

    def test_missing_font_fails_loud(self, og_client, monkeypatch):
        client, _cache, token, cache_dir = og_client
        _write_card(cache_dir, SAMPLE_CARD)
        monkeypatch.setattr(
            views_routes,
            "get_config",
            lambda: {
                "web": {
                    "og_font_path": "/nonexistent/font.ttf",
                    "og_font_bold_path": "/nonexistent/font-bold.ttf",
                }
            },
        )
        strict_client = TestClient(client.app, raise_server_exceptions=False)
        response = strict_client.get(f"/og/{token}.png")
        assert response.status_code == 500
