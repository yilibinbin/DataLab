from __future__ import annotations

import os
import sys
from pathlib import Path

# Ensure the DataLab project root is importable regardless of pytest rootdir/import-mode.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Test environment: default DATALAB_DEBUG=1 so the _security_shim
# unsafe-mode fallback is available when a future refactor breaks
# ``app_web.security``. Production keeps this unset — a broken
# security import raises RuntimeError and refuses to start.
# Contributors running the full suite don't need to remember the env
# var; specific tests can still override via
# ``DATALAB_DEBUG=0 pytest tests/...``.
os.environ.setdefault("DATALAB_DEBUG", "1")
