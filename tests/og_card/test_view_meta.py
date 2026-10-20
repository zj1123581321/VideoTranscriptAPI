"""View-page OG/Twitter meta tags for GET /view/{view_token}.

Wires the real views router against a real CacheManager on tmp_path,
matching tests/og_card/test_og_route.py. Meta tags are read via
BeautifulSoup; presence is never judged by raw substring search.

All console output must be in English only (no emoji, no Chinese).
"""

import json
import os
import shutil
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
from bs4 import BeautifulSoup
from fastapi import FastAPI
from fastapi.testclient import TestClient

from video_transcript_api.api.routes import views as views_routes
from video_transcript_api.cache.cache_manager import CacheManager
from video_transcript_api.utils.rendering import og_card

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

SPECIAL_CARD = {
    "version": 1,
    "headline": 'Foo "bar" <baz> & qux',
    "points": [
        'First "point" with <tag> & amp',
        "second point stays plain",
    ],
    "generated_at": "2026-10-16T12:00:00+08:00",
}

IMAGE_META_NAMES = ("twitter:card", "twitter:image:alt")
IMAGE_META_PROPERTIES = ("og:image", "og:image:width", "og:image:height")


def _write_card(cache_dir: Path, card) -> Path:
    path = cache_dir / og_card.CARD_FILENAME
    path.write_text(json.dumps(card, ensure_ascii=False), encoding="utf-8")
    return path


def _soup(response) -> BeautifulSoup:
    return BeautifulSoup(response.text, "html.parser")


def _meta_content(soup: BeautifulSoup, *, name=None, property=None):
    attrs = {}
    if name is not None:
        attrs["name"] = name
    if property is not None:
        attrs["property"] = property
    tag = soup.find("meta", attrs=attrs)
    if tag is None or not tag.has_attr("content"):
        return None
    return tag["content"]


def _image_metas(soup: BeautifulSoup) -> dict:
    found = {}
    for name in IMAGE_META_NAMES:
        value = _meta_content(soup, name=name)
        if value is not None:
            found[name] = value
    for prop in IMAGE_META_PROPERTIES:
        value = _meta_content(soup, property=prop)
        if value is not None:
            found[prop] = value
    return found


@pytest.fixture
def view_client(tmp_path, monkeypatch):
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
        author="AI lab",
        description="demo description",
    )
    cache.update_task_status(
        task_info["task_id"],
        "success",
        platform="youtube",
        media_id="abc123",
        title="DeepSeek-R2 深度实测",
    )
    cache_data = cache.get_cache(platform="youtube", media_id="abc123")
    assert cache_data is not None
    cache_dir = Path(cache_data["file_path"])

    monkeypatch.setattr(views_routes, "cache_manager", cache)
    monkeypatch.setattr(views_routes, "get_base_url", lambda: SITE_URL)

    app = FastAPI()
    app.include_router(views_routes.router)
    client = TestClient(app)
    yield client, cache, task_info["view_token"], cache_dir
    client.close()
    cache.close()


class TestViewShareCardMeta:
    def test_valid_card_emits_large_image_tags(self, view_client):
        client, _cache, token, cache_dir = view_client
        json_path = _write_card(cache_dir, SAMPLE_CARD)
        expected_v = str(json_path.stat().st_mtime_ns)

        response = client.get(f"/view/{token}")
        assert response.status_code == 200
        soup = _soup(response)
        metas = _image_metas(soup)

        assert metas["twitter:card"] == "summary_large_image"
        assert metas["og:image:width"] == "1200"
        assert metas["og:image:height"] == "630"
        assert metas["twitter:image:alt"] == SAMPLE_CARD["headline"]
        assert _meta_content(soup, property="og:description") == SAMPLE_CARD["points"][0]

        image_url = metas["og:image"]
        parsed = urlparse(image_url)
        assert image_url.startswith(SITE_URL)
        assert parsed.path == f"/og/{token}.png"
        assert parse_qs(parsed.query) == {"v": [expected_v]}
        assert expected_v.isdigit()

    def test_missing_card_omits_share_tags(self, view_client):
        client, _cache, token, _cache_dir = view_client
        response = client.get(f"/view/{token}")
        assert response.status_code == 200
        soup = _soup(response)
        assert _image_metas(soup) == {}
        assert _meta_content(soup, property="og:description") == (
            "DeepSeek-R2 深度实测 的转录校对结果"
        )

    def test_invalid_card_omits_share_tags(self, view_client):
        client, _cache, token, cache_dir = view_client
        _write_card(cache_dir, {**SAMPLE_CARD, "version": 2})
        response = client.get(f"/view/{token}")
        assert response.status_code == 200
        soup = _soup(response)
        assert _image_metas(soup) == {}
        assert _meta_content(soup, property="og:description") == (
            "DeepSeek-R2 深度实测 的转录校对结果"
        )

    def test_missing_cache_dir_omits_share_tags(self, view_client):
        client, _cache, token, cache_dir = view_client
        _write_card(cache_dir, SAMPLE_CARD)
        shutil.rmtree(cache_dir)
        response = client.get(f"/view/{token}")
        assert response.status_code == 200
        soup = _soup(response)
        assert _image_metas(soup) == {}
        og_desc = _meta_content(soup, property="og:description")
        assert og_desc is not None
        assert og_desc != SAMPLE_CARD["points"][0]

    def test_special_chars_are_escaped_in_meta(self, view_client):
        client, _cache, token, cache_dir = view_client
        _write_card(cache_dir, SPECIAL_CARD)
        response = client.get(f"/view/{token}")
        assert response.status_code == 200
        soup = _soup(response)

        alt = soup.find("meta", attrs={"name": "twitter:image:alt"})
        desc = soup.find("meta", attrs={"property": "og:description"})
        assert alt is not None and desc is not None
        assert alt["content"] == SPECIAL_CARD["headline"]
        assert desc["content"] == SPECIAL_CARD["points"][0]
        # Unescaped quotes would split the attribute; the parser would then
        # expose leftover tokens as extra attributes instead of one content.
        assert "bar" not in alt.attrs
        assert "point" not in desc.attrs
        assert "<tag>" not in str(desc)
        assert "<baz>" not in str(alt)

    def test_mtime_change_updates_cache_bust_query(self, view_client):
        client, _cache, token, cache_dir = view_client
        json_path = _write_card(cache_dir, SAMPLE_CARD)
        first = client.get(f"/view/{token}")
        assert first.status_code == 200
        first_url = _image_metas(_soup(first))["og:image"]
        first_v = parse_qs(urlparse(first_url).query)["v"][0]

        future = json_path.stat().st_mtime + 100
        os.utime(json_path, (future, future))
        second = client.get(f"/view/{token}")
        assert second.status_code == 200
        second_url = _image_metas(_soup(second))["og:image"]
        second_v = parse_qs(urlparse(second_url).query)["v"][0]

        assert first_v != second_v
        assert second_v == str(json_path.stat().st_mtime_ns)
        assert urlparse(first_url).path == urlparse(second_url).path

    def test_page_export_omits_share_tags(self, view_client):
        client, _cache, token, cache_dir = view_client
        _write_card(cache_dir, SAMPLE_CARD)
        response = client.get(f"/view/{token}", params={"page": "transcript"})
        assert response.status_code == 200
        soup = _soup(response)
        assert _image_metas(soup) == {}
        assert _meta_content(soup, property="og:description") != SAMPLE_CARD["points"][0]
        assert soup.find("meta", attrs={"name": "twitter:card"}) is None
