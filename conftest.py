"""Root-level pytest configuration.

Responsibilities:

- Ensure the DataLab project root is importable (mirrors ``tests/conftest.py``
  so tests can run from anywhere).
- Set ``DATALAB_DEBUG`` during test runs so ``app_web.server.create_app()``
  resolves a random-per-process SECRET_KEY without requiring an explicit
  ``DATALAB_WEB_SECRET``. This keeps the test suite hermetic while preserving
  the production invariant that a missing secret is a hard failure.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Mark this process as a development/test context so create_app generates a
# random SECRET_KEY instead of raising. Tests that specifically exercise the
# production refusal path still patch os.environ with `clear=True` to remove
# this flag.
os.environ.setdefault("DATALAB_DEBUG", "1")


def pytest_ignore_collect(collection_path, config):  # type: ignore[no-untyped-def]
    """Ignore local test-file duplicates produced by Finder-style conflict copies."""

    return collection_path.name.startswith("test_") and collection_path.name.endswith(" 2.py")
