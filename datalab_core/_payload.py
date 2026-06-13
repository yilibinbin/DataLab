from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from typing import Any


_SCALAR_TYPES = (str, int, bool, type(None))


class FrozenJsonDict(Mapping[str, Any]):
    """Immutable mapping used at core DTO boundaries."""

    __slots__ = ("_data",)

    def __init__(self, data: Mapping[str, Any]) -> None:
        self._data = dict(data)

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)

    def __repr__(self) -> str:
        return repr(self._data)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Mapping):
            return dict(self.items()) == dict(other.items())
        return False

    def __hash__(self) -> int:
        return hash(tuple((key, _hashable_json_value(value)) for key, value in sorted(self._data.items())))

    def __deepcopy__(self, memo: dict[int, Any]) -> dict[str, Any]:
        from copy import deepcopy

        return {key: deepcopy(value, memo) for key, value in self._data.items()}


class FrozenJsonList(Sequence[Any]):
    """Immutable JSON-array view used at core DTO boundaries."""

    __slots__ = ("_items",)

    def __init__(self, items: Sequence[Any]) -> None:
        self._items = tuple(items)

    def __getitem__(self, index: int | slice) -> Any:
        if isinstance(index, slice):
            return FrozenJsonList(self._items[index])
        return self._items[index]

    def __len__(self) -> int:
        return len(self._items)

    def __repr__(self) -> str:
        return repr(list(self._items))

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Sequence) and not isinstance(other, (str, bytes, bytearray, memoryview)):
            return list(self._items) == list(other)
        return False

    def __hash__(self) -> int:
        return hash(tuple(_hashable_json_value(item) for item in self._items))

    def __deepcopy__(self, memo: dict[int, Any]) -> list[Any]:
        from copy import deepcopy

        return [deepcopy(item, memo) for item in self._items]


def _hashable_json_value(value: Any) -> Any:
    if isinstance(value, FrozenJsonDict | FrozenJsonList):
        return value
    if isinstance(value, Mapping):
        return FrozenJsonDict(value)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray, memoryview)):
        return FrozenJsonList(value)
    return value


def normalize_json_payload(value: Any, *, path: str = "payload") -> Any:
    """Validate and copy JSON-like payloads before compute service entry.

    DataLab compute boundaries preserve user-entered numbers as strings until
    they are parsed under the selected precision context. Binary floats and
    non-JSON container types are rejected instead of being silently accepted.
    JSON objects and arrays are stored as immutable views; dataclass/asdict
    deep-copy output normalizes those views back to plain dictionaries/lists.
    """

    if isinstance(value, float):
        raise TypeError(f"JSON floats are not allowed at {path}; pass numeric inputs as strings.")
    if isinstance(value, _SCALAR_TYPES):
        return value
    if isinstance(value, Mapping):
        copied: dict[str, Any] = {}
        for key, item in value.items():
            key_path = f"{path}.<key>"
            if isinstance(key, float):
                raise TypeError(f"JSON floats are not allowed at {key_path}; pass mapping keys as strings.")
            if not isinstance(key, str):
                raise TypeError(f"Only string mapping keys are allowed at {key_path}.")
            copied[key] = normalize_json_payload(item, path=f"{path}.{key}")
        return FrozenJsonDict(copied)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray, memoryview)):
        copied_items: list[Any] = []
        for index, item in enumerate(value):
            copied_items.append(normalize_json_payload(item, path=f"{path}[{index}]"))
        return FrozenJsonList(copied_items)
    raise TypeError(
        f"Unsupported payload type at {path}: {type(value).__name__}. "
        "Use strings, integers, booleans, null, lists, and dictionaries."
    )


def validate_optional_int(value: int | None, *, field_name: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, float):
        raise TypeError(f"JSON floats are not allowed at {field_name}; pass integer options as integers.")
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer or None.")
    return value
