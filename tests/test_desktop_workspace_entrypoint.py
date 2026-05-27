from __future__ import annotations

from pathlib import Path


def test_workspace_paths_from_argv_keeps_first_datalab_path() -> None:
    from app_desktop.main import workspace_paths_from_argv

    first = Path("/tmp/case.datalab")
    second = Path("/tmp/second.DATALAB")

    assert workspace_paths_from_argv(["DataLab", "/tmp/notes.txt", str(first), str(second)]) == [
        first
    ]


def test_workspace_paths_from_argv_ignores_options_and_end_of_options() -> None:
    from app_desktop.main import workspace_paths_from_argv

    workspace = Path("/tmp/case.datalab")

    assert workspace_paths_from_argv(
        ["DataLab", "-psn_0_12345", "--debug", "--", str(workspace)]
    ) == [workspace]


def test_workspace_paths_from_argv_can_be_disabled_for_macos() -> None:
    from app_desktop.main import workspace_paths_from_argv

    assert workspace_paths_from_argv(["DataLab", "/tmp/case.datalab"], enabled=False) == []
