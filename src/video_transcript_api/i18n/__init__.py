"""User-visible interface text catalogs (i18n core).

One global ``language`` config key (top-level, values ``zh-CN`` / ``en``,
default ``zh-CN``) selects the catalog. ``t(key, **kwargs)`` renders a message
from that catalog; ``get_language()`` reports the effective language.

Contract for consumers (C3/C4/C5) -- these names are frozen:

* ``SUPPORTED_LANGUAGES``: tuple of supported language tags.
* ``DEFAULT_LANGUAGE``: tag used when the config has no ``language`` key.
* ``get_language() -> str``: the effective language, validated on every call.
* ``t(key, **kwargs) -> str``: text for ``key`` with ``str.format`` style named
  placeholders. An unknown key raises ``KeyError`` -- there is deliberately no
  fallback to the key itself and no fallback to another language, so a missing
  translation fails loudly instead of shipping a half-English UI.

Adding a language
-----------------
1. Add ``locales/<tag>.json`` next to the existing catalogs, UTF-8 encoded,
   with the same flat dot-separated keys (``{"web.nav.history": "History"}``).
   The key set must match the other catalogs exactly -- tests/unit/i18n
   compares them.
2. Append ``<tag>`` to ``SUPPORTED_LANGUAGES``.

Catalogs are loaded once per language on first use and cached in-process; they
are read-only data, so there is no reset hook. Changing the language at runtime
only requires changing the config value, not clearing this cache.
"""

import json
from pathlib import Path
from typing import Any

#: Language used when the config has no ``language`` key (all existing
#: deployments predate the key and must keep their current Chinese output).
DEFAULT_LANGUAGE = "zh-CN"

#: Every language that has a catalog in ``locales/``.
SUPPORTED_LANGUAGES = ("zh-CN", "en")

_LOCALES_DIR = Path(__file__).resolve().parent / "locales"

# Loaded catalogs, keyed by language tag. Read-only after first load.
_catalogs: dict[str, dict[str, str]] = {}


def validate_language(value: Any) -> str:
    """Return ``value`` if it is a supported language tag, else raise.

    The error message always lists the legal values, because the only way a
    user sees it is a startup failure on a typo in their config file.

    Raises:
        ValueError: ``value`` is not one of ``SUPPORTED_LANGUAGES``.
    """
    if not isinstance(value, str) or value not in SUPPORTED_LANGUAGES:
        supported = ", ".join(SUPPORTED_LANGUAGES)
        raise ValueError(
            f"unsupported language {value!r}: supported values are {supported}"
        )
    return value


def get_language() -> str:
    """Return the validated global language from the loaded configuration.

    The value is re-validated on every call (a tuple membership check), so a
    config mutated after load still cannot silently select an unknown catalog.

    Raises:
        ValueError: the configured language is not supported.
    """
    # Imported here, not at module level: utils.logging.logger imports this
    # module to validate the config it just parsed, so a module-level import of
    # load_config here would be a cycle.
    from ..utils.logging.logger import load_config

    return validate_language(load_config().get("language", DEFAULT_LANGUAGE))


def _catalog(language: str) -> dict[str, str]:
    """Return the catalog for ``language``, loading it on first use."""
    catalog = _catalogs.get(language)
    if catalog is None:
        path = _LOCALES_DIR / f"{language}.json"
        with path.open("r", encoding="utf-8") as handle:
            catalog = json.load(handle)
        _catalogs[language] = catalog
    return catalog


def t(key: str, **kwargs: Any) -> str:
    """Return the text for ``key`` in the current language.

    Args:
        key: flat dot-separated catalog key, e.g. ``"common.language_name"``.
        **kwargs: values for ``str.format`` style named placeholders.

    Returns:
        The rendered text.

    Raises:
        KeyError: ``key`` is absent from the catalog, or a placeholder in the
            template has no matching keyword argument.
    """
    language = get_language()
    try:
        template = _catalog(language)[key]
    except KeyError:
        raise KeyError(f"missing i18n key {key!r} for language {language!r}") from None
    return template.format(**kwargs)
