"""Unit tests for the PWA web app manifest and icon assets (PWA T3).

Contract (design: docs/designs/pwa.md -- adjudicated values, do not change):
- ``id`` / ``start_url`` are ``/add_task_by_web`` (unified entry; stable id so
  manifest updates are not detected as a new app);
- ``scope`` is ``/`` so /view/ result pages stay inside the PWA window;
- ``display`` is ``standalone`` (the default ``browser`` would keep opening
  in a tab, defeating the install);
- ``share_target`` uses GET against ``/add_task_by_web`` and declares all
  three params (url/title/text) -- a missing ``action`` makes browsers drop
  the whole member;
- every icon referenced by the manifest (plus the 180px apple-touch-icon)
  must exist on disk -- a missing icon fails installation silently.

All console output must be pure English (no emoji, no Chinese).
"""

import json

from video_transcript_api.api.context import get_static_dir


def _load_manifest() -> dict:
    manifest_path = get_static_dir() / "manifest.webmanifest"
    assert manifest_path.exists(), f"manifest not found: {manifest_path}"
    return json.loads(manifest_path.read_text(encoding="utf-8"))


class TestManifestRequiredFields:
    def test_identity_and_entry(self):
        m = _load_manifest()
        assert m["id"] == "/add_task_by_web"
        assert m["start_url"] == "/add_task_by_web"
        assert m["scope"] == "/"
        assert m["display"] == "standalone"
        assert m["name"]
        assert m["short_name"]

    def test_brand_colors(self):
        m = _load_manifest()
        assert m["theme_color"] == "#4f46e5"
        assert m["background_color"] == "#ffffff"

    def test_share_target(self):
        m = _load_manifest()
        share = m["share_target"]
        assert share["action"] == "/add_task_by_web"
        assert share["method"] == "GET"
        params = share["params"]
        assert params["url"] == "url"
        assert params["title"] == "title"
        assert params["text"] == "text"

    def test_shortcuts(self):
        m = _load_manifest()
        urls = {s["url"] for s in m["shortcuts"]}
        assert "/add_task_by_web" in urls
        assert "/static/history.html" in urls


class TestManifestIconsExist:
    def test_manifest_icons_exist_on_disk(self):
        m = _load_manifest()
        static_dir = get_static_dir()
        assert m["icons"], "manifest must declare icons"
        for icon in m["icons"]:
            src = icon["src"]
            assert src.startswith("/static/"), f"unexpected icon src: {src}"
            path = static_dir / src.removeprefix("/static/")
            assert path.exists(), f"icon file missing: {path}"

    def test_required_icon_sizes_and_maskable(self):
        m = _load_manifest()
        sizes = {icon["sizes"] for icon in m["icons"]}
        assert "192x192" in sizes
        assert "512x512" in sizes
        purposes = {icon.get("purpose", "any") for icon in m["icons"]}
        assert "maskable" in purposes

    def test_apple_touch_icon_exists(self):
        path = get_static_dir() / "icons" / "apple-touch-icon.png"
        assert path.exists(), f"apple-touch-icon missing: {path}"
