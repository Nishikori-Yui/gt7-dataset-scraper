import os
import warnings

_EMITTED: set[str] = set()


def warn_compat(module_name: str, replacement: str) -> None:
    if os.environ.get("GT7DB_DISABLE_COMPAT_WARNINGS", "").lower() in {"1", "true", "yes", "on"}:
        return
    key = f"{module_name}->{replacement}"
    if key in _EMITTED:
        return
    _EMITTED.add(key)
    warnings.warn(
        f"'{module_name}' is a compatibility module and may be removed in a future release; use '{replacement}' instead.",
        DeprecationWarning,
        stacklevel=2,
    )
