"""Install C1 catalog helpers onto a Jinja2 environment.

Templates call ``t(key, **kwargs)``, ``html_lang()`` and ``og_locale()``.
The callables read the request-scoped public-page language when set and the
configured site language otherwise; the shared Jinja environment is unchanged.
"""

from ...i18n import get_ui_language, t


def html_lang() -> str:
    """Return the current UI language tag for ``<html lang>``."""
    return get_ui_language()


def og_locale() -> str:
    """Return the Open Graph locale (``zh_CN`` / ``en``)."""
    return "en" if get_ui_language() == "en" else "zh_CN"


def install_i18n(env) -> None:
    """Expose catalog helpers as Jinja globals on ``env``."""
    env.globals["t"] = t
    env.globals["html_lang"] = html_lang
    env.globals["og_locale"] = og_locale
