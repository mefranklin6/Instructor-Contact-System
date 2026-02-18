"""Helpers for loading plugin factories.

External plugins are referenced via `module:attribute` strings.
"""

import importlib
from typing import Any


def import_from_spec(spec: str) -> Any:
    """Import an attribute from a `module:attr` spec.

    Args:
        spec: Import spec like `my_pkg.my_mod:create`.

    Returns:
        Imported object.

    Raises:
        ValueError: If the spec is not in `module:attr` form.
    """

    if ":" not in spec:
        raise ValueError(f"External plugins must be specified as 'module:attribute' (got {spec!r}).")

    module_name, attr_name = spec.split(":", 1)
    module = importlib.import_module(module_name)
    return getattr(module, attr_name)
