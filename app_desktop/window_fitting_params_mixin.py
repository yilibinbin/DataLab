"""Reusable fitting-parameter table concern.

Parameter editing now lives in :mod:`app_desktop.parameter_table`.  This mixin
remains as a stable MRO slot for the desktop window while production behavior is
implemented by the window methods that delegate to ``ParameterTable`` widgets.
"""

from __future__ import annotations


class WindowFittingParamsMixin:
    pass
