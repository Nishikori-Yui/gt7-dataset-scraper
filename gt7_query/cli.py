from .compat._warnings import warn_compat

warn_compat("gt7_query.cli", "gt7_query.app.query_cli")

from .app.query_cli import *  # noqa: F401,F403
