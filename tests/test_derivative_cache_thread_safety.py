from __future__ import annotations

from collections import OrderedDict
from importlib import import_module

import pytest


class GuardedOrderedDict(OrderedDict):
    def __init__(self, lock) -> None:
        super().__init__()
        self._lock = lock

    def _assert_locked(self) -> None:
        assert self._lock.locked(), "symbolic derivative cache accessed without lock"

    def __contains__(self, key: object) -> bool:
        self._assert_locked()
        return super().__contains__(key)

    def __getitem__(self, key):
        self._assert_locked()
        return super().__getitem__(key)

    def __setitem__(self, key, value) -> None:
        self._assert_locked()
        super().__setitem__(key, value)

    def __len__(self) -> int:
        self._assert_locked()
        return super().__len__()

    def move_to_end(self, key, last: bool = True) -> None:
        self._assert_locked()
        super().move_to_end(key, last=last)

    def popitem(self, last: bool = True):
        self._assert_locked()
        return super().popitem(last=last)


@pytest.mark.parametrize("module_name", ["shared.derivatives", "datalab_latex.derivatives"])
def test_symbolic_derivative_caches_are_lock_guarded(module_name: str, monkeypatch: pytest.MonkeyPatch) -> None:
    module = import_module(module_name)
    lock = module._SYMBOLIC_CACHE_LOCK

    partials_cache = GuardedOrderedDict(lock)
    hessian_cache = GuardedOrderedDict(lock)
    monkeypatch.setattr(module, "_SYMBOLIC_PARTIALS_CACHE", partials_cache)
    monkeypatch.setattr(module, "_SYMBOLIC_HESSIAN_CACHE", hessian_cache)
    monkeypatch.setattr(module, "_build_symbolic_partials", lambda _formula, _variables: [None])
    monkeypatch.setattr(module, "_build_symbolic_hessian", lambda _formula, _variables: [[None]])

    assert module._get_symbolic_partials("x", ["x"]) == [None]
    assert module._get_symbolic_partials("x", ["x"]) == [None]
    assert module._get_symbolic_hessian("x", ["x"]) == [[None]]
    assert module._get_symbolic_hessian("x", ["x"]) == [[None]]

