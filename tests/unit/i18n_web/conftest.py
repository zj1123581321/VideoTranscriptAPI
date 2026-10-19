"""Shared language-config fixture for C4 i18n web tests."""

import pytest

from video_transcript_api.utils.logging.logger import load_config


@pytest.fixture
def language_config():
    """Set/clear the global ``language`` key on the process-wide config."""
    config = load_config()
    had_key = "language" in config
    original = config.get("language")

    def _set(value):
        if value is None:
            config.pop("language", None)
        else:
            config["language"] = value

    try:
        yield _set
    finally:
        if had_key:
            config["language"] = original
        else:
            config.pop("language", None)
