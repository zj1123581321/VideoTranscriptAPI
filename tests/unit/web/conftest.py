"""Install C1 catalog helpers on every Jinja environment in this suite."""

import jinja2

from video_transcript_api.utils.rendering.i18n_jinja import install_i18n

_orig_init = jinja2.Environment.__init__


def _init(self, *args, **kwargs):
    _orig_init(self, *args, **kwargs)
    install_i18n(self)


jinja2.Environment.__init__ = _init
