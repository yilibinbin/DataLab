"""DataLab CLI — non-interactive batch entry point.

Allows DataLab's scientific workflows to be scripted from a YAML
config, for use in labs integrating DataLab into automation
pipelines (CI data validation, nightly fit re-runs, headless
notebooks).

The CLI never imports PySide6 — it runs fully headless. The
computation core is shared with the desktop GUI via
``app_desktop.workers_core`` (the ``_execute_*_job`` pure functions),
but the CLI reaches those directly, not through Qt workers.
"""

__all__ = ["main"]


from .main import main  # noqa: E402
