from __future__ import annotations

import pytest


def test_data_extrapolation_gui_shim_exports_public_names_only():
    pytest.importorskip("PySide6")

    import data_extrapolation_gui as shim

    assert callable(shim.main)
    assert shim.ExtrapolationWindow is not None
    assert set(shim.__all__) <= set(dir(shim))

    private = [name for name in dir(shim) if name.startswith("_") and not name.startswith("__")]
    assert private == []
