from .compat._warnings import warn_compat

warn_compat("gt7_query.queries", "gt7_query.compat.queries")

from .compat.queries import *  # noqa: F401,F403
