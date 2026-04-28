"""Backward-compatible entry point for the DART termsheet downloader.

The implementation lives under :mod:`dart_app`.  Importing ``dart_auto`` returns
the legacy-compatible module so existing tests, tools, and user scripts can keep
patching module globals such as ``CACHE_DIR`` and ``SETTINGS_PATH``.
"""
from __future__ import annotations

import sys as _sys

from dart_app import legacy as _legacy

if __name__ == "__main__":
    _legacy.main()
else:
    _sys.modules[__name__] = _legacy
