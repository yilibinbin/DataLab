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
#
# Limitation: a test that wants to pin the *production fail-fast*
# behaviour cannot ``monkeypatch.delenv("DATALAB_DEBUG")`` and re-
# import ``_security_shim`` — Python's import cache makes the env
# var only read once at first import, and that import is already
# done by the time the test runs. Such tests must spawn a fresh
# Python subprocess with a clean environment, e.g.::
#
#     subprocess.run(
#         [sys.executable, "-c", "import app_web.server"],
#         env={"PATH": os.environ["PATH"]},  # NO DATALAB_DEBUG
#         check=False,
#     )
#
# and inspect the return code / stderr there.
os.environ.setdefault("DATALAB_DEBUG", "1")
