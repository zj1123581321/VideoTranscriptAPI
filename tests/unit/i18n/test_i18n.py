"""i18n core: global ``language`` config, flat text catalogs and ``t()``.

Locks the shared contract that C3/C4/C5 consume:

1. ``language`` is one global key, default ``zh-CN``; an unsupported value
   fails at config load time (fail fast), not at the first ``t()`` call.
2. ``t(key, **kwargs)`` never falls back: a missing key raises instead of
   returning the key itself or the same text in another language.
3. Both locale files carry exactly the same key set.

All console output must be in English only (no emoji, no Chinese).
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from video_transcript_api.i18n import (
    DEFAULT_LANGUAGE,
    SUPPORTED_LANGUAGES,
    get_language,
    t,
)
from video_transcript_api.utils.logging.logger import load_config

PROJECT_ROOT = Path(__file__).resolve().parents[3]
MAIN_PY = PROJECT_ROOT / "main.py"
LOCALES_DIR = PROJECT_ROOT / "src" / "video_transcript_api" / "i18n" / "locales"


@pytest.fixture
def language_config():
    """Set/clear the global ``language`` key on the process-wide config.

    ``load_config()`` returns the single cached dict, so mutating it in place is
    the real path ``get_language()`` reads; the original state is restored in
    ``finally`` so a failing assertion cannot leak the language into other
    tests (same approach as tests/unit/test_timezone.py).
    """
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


def _read_catalog(language):
    path = LOCALES_DIR / f"{language}.json"
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def test_supported_languages_contract_is_locked():
    """The public tuple is what C3/C4/C5 import; renaming breaks them."""
    assert SUPPORTED_LANGUAGES == ("zh-CN", "en")
    assert DEFAULT_LANGUAGE == "zh-CN"


def test_locale_files_have_identical_key_sets():
    """A key added to one language only must fail here, not at runtime."""
    catalogs = {language: _read_catalog(language) for language in SUPPORTED_LANGUAGES}
    key_sets = {language: set(catalog) for language, catalog in catalogs.items()}

    reference_language = DEFAULT_LANGUAGE
    for language, keys in key_sets.items():
        assert keys == key_sets[reference_language], (
            f"locale {language} key set differs from {reference_language}: "
            f"missing={sorted(key_sets[reference_language] - keys)} "
            f"extra={sorted(keys - key_sets[reference_language])}"
        )
    assert key_sets[reference_language], "locale catalogs must not be empty"
    for language, catalog in catalogs.items():
        for key, text in catalog.items():
            assert isinstance(text, str) and text.strip(), f"{language}:{key}"


def test_missing_language_config_defaults_to_zh_cn(language_config):
    """Existing deployments have no ``language`` key and must stay Chinese."""
    language_config(None)

    assert get_language() == "zh-CN"
    assert t("common.language_name") == "中文"


def test_language_en_switches_catalog(language_config):
    language_config("en")

    assert get_language() == "en"
    assert t("common.language_name") == "English"


def test_config_load_rejects_unsupported_language(tmp_path):
    """An unsupported value fails at load time and lists the legal values."""
    config_path = tmp_path / "config.jsonc"
    config_path.write_text(json.dumps({"language": "fr"}), encoding="utf-8")

    with pytest.raises(ValueError) as excinfo:
        load_config(config_path, use_cache=False)

    message = str(excinfo.value)
    assert "'fr'" in message, message
    assert "zh-CN, en" in message, message


def test_non_object_config_root_keeps_its_own_error(tmp_path):
    """The language check must not hijack the root-shape error.

    ``validate_config`` owns ``"configuration root must be an object"``. A
    non-dict root therefore has to reach it unchanged; otherwise the user sees
    ``TypeError: argument of type 'int' is not iterable``, which names neither
    the file nor the real problem (regression caught in review of the first
    round of this card).
    """
    config_path = tmp_path / "config.jsonc"
    config_path.write_text("123", encoding="utf-8")

    # load_config itself must not raise on the shape: it has no say over it.
    # The call is wrapped in try/except only so the failure surfaces as a failed
    # assertion rather than an unrelated exception type: the assertion is what
    # this test is about, and a bare call would turn a regression into an
    # Error (not a Failure) with no diff to read.
    raised = None
    try:
        parsed = load_config(config_path, use_cache=False)
    except Exception as exc:  # noqa: BLE001 - re-asserted immediately below
        raised = exc
        parsed = None
    assert raised is None, f"load_config must not judge the config root shape: {raised!r}"
    assert parsed == 123

    from video_transcript_api.api.context import ConfigError, validate_config

    with pytest.raises(ConfigError) as excinfo:
        validate_config(123)
    assert "configuration root must be an object" in str(excinfo.value)


def test_get_language_rejects_unsupported_language(language_config):
    """Even a mutated in-memory config cannot silently produce a wrong locale."""
    language_config("fr")

    with pytest.raises(ValueError) as excinfo:
        get_language()
    assert "zh-CN, en" in str(excinfo.value)


def test_t_raises_on_missing_key(language_config):
    """No fallback to the key itself and no fallback to another language."""
    language_config("zh-CN")

    with pytest.raises(KeyError) as excinfo:
        t("common.no_such_key")

    assert "common.no_such_key" in str(excinfo.value)


def test_t_formats_named_placeholders(language_config):
    language_config("zh-CN")
    assert t("common.language_selected", language="中文") == "界面语言：中文"

    language_config("en")
    assert t("common.language_selected", language="English") == "UI language: English"

    with pytest.raises(KeyError):
        t("common.language_selected")


def _minimal_config(tmp_path):
    """Minimal config that passes ``validate_config`` (mirrors the proven
    fixture in tests/unit/test_check_config_effective_values.py). All paths
    stay under tmp_path so no real runtime directory is written."""
    return {
        "api": {
            "host": "127.0.0.1",
            "port": 8000,
            "auth_token": "test-auth-token",
        },
        "concurrent": {"max_workers": 1, "queue_size": 2, "llm_max_workers": 1},
        "storage": {
            "cache_dir": str(tmp_path / "cache"),
            "workspace_dir": str(tmp_path / "workspace"),
            "temp_dir": str(tmp_path / "temp"),
            "audit_db": str(tmp_path / "audit.db"),
        },
        "web": {"base_url": "http://localhost:8000"},
        "llm": {
            "api_key": "test-llm-api-key",
            "base_url": "http://127.0.0.1:1/v1",
            "calibrate_model": "calibrate-model",
            "summary_model": "summary-model",
        },
        "wechat": {"webhook": "http://127.0.0.1:1/wechat"},
        "tikhub": {"enabled": False, "api_key": "test-tikhub-key"},
        "log": {"file": str(tmp_path / "app.log")},
    }


def _run_check_config(tmp_path, config):
    """Real subprocess: ``main.py --check-config`` is the startup preflight."""
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(Path(os.environ.get("HOME", "/tmp"))),
        "LANG": "C.UTF-8",
    }
    return subprocess.run(
        [
            sys.executable,
            str(MAIN_PY),
            "--check-config",
            "--config",
            str(config_path),
        ],
        cwd=str(PROJECT_ROOT),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_check_config_accepts_default_language(tmp_path):
    """No ``language`` key: the preflight must stay green (zh-CN default)."""
    result = _run_check_config(tmp_path, _minimal_config(tmp_path))

    assert result.returncode == 0, result.stderr
    assert "Configuration OK" in result.stdout


def test_check_config_rejects_unsupported_language(tmp_path):
    """The real startup preflight must fail and name the legal values."""
    config = _minimal_config(tmp_path)
    config["language"] = "fr"

    result = _run_check_config(tmp_path, config)

    assert result.returncode != 0, result.stdout
    assert "Configuration OK" not in result.stdout
    combined = result.stdout + result.stderr
    assert "zh-CN, en" in combined, combined


def _run_i18n_probe(tmp_path, config):
    """Read ``t()``/``get_language()`` in a fresh subprocess reading ``config``.

    Separate from ``--check-config`` on purpose: that preflight only proves the
    value is accepted, not that a ``"en"`` config actually makes ``t()`` return
    English. This is the consumer-side half of the contract, in its own process,
    so a module-level cache left over from another test cannot mask it.
    """
    config_path = tmp_path / "probe-config.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(Path(os.environ.get("HOME", "/tmp"))),
        "LANG": "C.UTF-8",
        "VTAPI_CONFIG": str(config_path),
        # main.py inserts <repo>/src itself; a bare -c probe has to do the same.
        "PYTHONPATH": str(PROJECT_ROOT / "src"),
    }
    code = (
        "import json\n"
        "from video_transcript_api.i18n import get_language, t\n"
        "print(json.dumps({\n"
        "    'language': get_language(),\n"
        "    'name': t('common.language_name'),\n"
        "    'selected': t('common.language_selected', language='X'),\n"
        "}))\n"
    )
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(PROJECT_ROOT),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_en_config_file_makes_t_return_english(tmp_path):
    """The behavioural acceptance clause: ``"en"`` in the config file is enough.

    Reads through ``VTAPI_CONFIG`` (the real env var main.py sets for
    ``--start``) rather than mutating the cached dict, so this covers the
    file -> load_config -> get_language -> catalog path end to end.
    """
    config = _minimal_config(tmp_path)
    config["language"] = "en"

    result = _run_i18n_probe(tmp_path, config)

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload["language"] == "en", payload
    assert payload["name"] == "English", payload
    assert payload["selected"] == "UI language: X", payload


def test_missing_language_key_keeps_chinese_end_to_end(tmp_path):
    """Default stays zh-CN through the real env-var path, not just the fixture."""
    result = _run_i18n_probe(tmp_path, _minimal_config(tmp_path))

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload["language"] == "zh-CN", payload
    assert payload["name"] == "中文", payload
    assert payload["selected"] == "界面语言：X", payload
