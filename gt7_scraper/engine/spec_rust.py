from ..compat._warnings import warn_compat

warn_compat("gt7_scraper.engine.spec_rust", "gt7_scraper.backends.spec.rust_normalizer")

from ..backends.spec.rust_normalizer import (  # noqa: F401
    normalize_codes_with_rust,
    normalize_specs_with_rust,
    resolve_rust_spec_binary,
)
