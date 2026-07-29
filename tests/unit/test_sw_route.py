"""Unit tests for the root-level ``GET /sw.js`` route (PWA T2).

The service worker script must be served from the root path so its scope
covers ``/`` (a worker at ``/static/sw.js`` could only control ``/static/``).
Contract (design: docs/designs/pwa.md):
- HTTP 200 and anonymous access (no Authorization header -- SW registration
  would fail otherwise);
- explicit ``Cache-Control: no-cache`` so browsers always revalidate;
- a JavaScript content type.

All console output must be pure English (no emoji, no Chinese).
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def _minimal_llm_config() -> dict:
    """Smallest llm section satisfying LLMConfig.from_dict's hard keys;
    base_url points at a closed local port so nothing reaches the network."""
    return {
        "api_key": "test-llm-key",
        "base_url": "http://127.0.0.1:1/v1",
        "calibrate_model": "test-calibrate-model",
        "summary_model": "test-summary-model",
    }


def _minimal_config(tmp_path: Path) -> dict:
    return {
        "api": {"host": "127.0.0.1", "port": 8000, "auth_token": "test-token"},
        "concurrent": {"max_workers": 1, "queue_size": 2, "llm_max_workers": 1},
        "storage": {
            "cache_dir": str(tmp_path / "cache"),
            "workspace_dir": str(tmp_path / "workspace"),
            "temp_dir": str(tmp_path / "temp"),
            "audit_db": str(tmp_path / "audit.db"),
        },
        "web": {"base_url": "http://localhost:8000"},
        "llm": _minimal_llm_config(),
        "log": {"file": str(tmp_path / "app.log")},
    }


class TestServiceWorkerRoute:
    @pytest.fixture
    def client(self, tmp_path):
        from video_transcript_api.api.app import create_app

        config = _minimal_config(tmp_path)
        app = create_app(config_loader=lambda: config, start_background=False)
        with TestClient(app) as test_client:
            yield test_client

    def test_sw_js_returns_200(self, client):
        resp = client.get("/sw.js")
        assert resp.status_code == 200

    def test_sw_js_anonymous_access(self, client):
        """No Authorization header must still succeed (incognito window)."""
        resp = client.get("/sw.js", headers={"Authorization": ""})
        assert resp.status_code == 200

    def test_sw_js_has_no_cache_header(self, client):
        resp = client.get("/sw.js")
        assert resp.headers["Cache-Control"] == "no-cache"

    def test_sw_js_content_type_is_javascript(self, client):
        resp = client.get("/sw.js")
        assert "javascript" in resp.headers["Content-Type"]
