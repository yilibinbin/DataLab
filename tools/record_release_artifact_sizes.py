#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import posixpath
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlsplit


DEFAULT_ROOT = "dist"
ARTIFACT_SUFFIXES = (".app", ".pkg", ".dmg", ".zip", ".exe", ".msi")


def _artifact_size(path: Path) -> int:
    if path.is_file():
        return path.lstat().st_size
    if path.is_dir():
        total = 0
        for child in path.rglob("*"):
            if child.is_file() or child.is_symlink():
                total += child.lstat().st_size
        return total
    raise FileNotFoundError(path)


def _human_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KiB", "MiB", "GiB"):
        if value < 1024.0 or unit == "GiB":
            if unit == "B":
                return f"{int(value)} {unit}"
            return f"{value:.1f} {unit}"
        value /= 1024.0
    return f"{value:.1f} GiB"


def discover_artifacts(repo_root: Path, roots: Iterable[str] = (DEFAULT_ROOT,)) -> list[Path]:
    artifacts: list[Path] = []
    for root_name in roots:
        root = repo_root / root_name
        if not root.exists():
            continue
        for suffix in ARTIFACT_SUFFIXES:
            artifacts.extend(path for path in root.glob(f"*{suffix}") if path.is_file() or path.is_dir())
    return sorted(set(artifacts))


def build_manifest(repo_root: Path, artifacts: Iterable[Path]) -> dict[str, object]:
    repo_root = repo_root.resolve()
    entries = []
    for artifact in sorted(artifacts):
        path = artifact.resolve()
        if not path.is_relative_to(repo_root):
            raise ValueError(f"Release artifact is outside the repository root: {path}")
        size = _artifact_size(path)
        entries.append(
            {
                "path": path.relative_to(repo_root).as_posix(),
                "bytes": size,
                "human_size": _human_size(size),
            }
        )
    return {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "artifact_count": len(entries),
        "artifacts": entries,
    }


def validate_artifact_size_manifest(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        raise ValueError("Artifact size manifest must be a JSON object")
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list):
        raise ValueError("Artifact size manifest must contain an artifacts list")
    if not artifacts:
        raise ValueError("Artifact size manifest must contain at least one artifact")
    artifact_count = payload.get("artifact_count")
    if artifact_count != len(artifacts):
        raise ValueError("Artifact size manifest artifact_count does not match artifacts")

    rows = []
    seen: set[str] = set()
    for index, row in enumerate(artifacts):
        if not isinstance(row, dict):
            raise ValueError(f"Artifact row {index} must be a JSON object")
        path = _validate_artifact_manifest_path(row.get("path"))
        if path in seen:
            raise ValueError(f"Duplicate artifact path in manifest: {path}")
        seen.add(path)
        bytes_value = row.get("bytes")
        if not isinstance(bytes_value, int) or bytes_value < 0:
            raise ValueError(f"Artifact bytes must be a non-negative integer for {path}")
        human_size = row.get("human_size")
        if not isinstance(human_size, str) or not human_size.strip():
            raise ValueError(f"Artifact human_size must be a non-empty string for {path}")
        normalized = dict(row)
        normalized.update({"path": path, "bytes": bytes_value, "human_size": human_size.strip()})
        rows.append(normalized)
    return rows


def _validate_artifact_manifest_path(value: Any) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("Artifact path must be a non-empty string")
    if "\\" in value or "\x00" in value:
        raise ValueError(f"Artifact path is not portable: {value!r}")
    parsed = urlsplit(value)
    if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment:
        raise ValueError(f"Artifact path must be repo-relative, not a URL: {value!r}")
    path = Path(value)
    if path.is_absolute():
        raise ValueError(f"Artifact path must be repo-relative: {value!r}")
    normalized = posixpath.normpath(value)
    if normalized in {".", ".."} or normalized.startswith("../") or normalized != value:
        raise ValueError(f"Artifact path must be normalized under the repository: {value!r}")
    return normalized


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Record DataLab release artifact sizes as JSON.")
    parser.add_argument("artifacts", nargs="*", type=Path, help="Artifacts to record. Defaults to scanning top-level dist/ outputs.")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd(), help="Repository root for relative output paths.")
    parser.add_argument("--out", type=Path, help="Optional JSON output path.")
    parser.add_argument(
        "--allow-empty",
        action="store_true",
        help="Write an empty diagnostic manifest when no artifacts are found. Do not use for release evidence.",
    )
    args = parser.parse_args(argv)

    repo_root = args.repo_root.resolve()
    artifacts = [path.resolve() for path in args.artifacts] if args.artifacts else discover_artifacts(repo_root)
    if not artifacts and not args.allow_empty:
        print(
            "No release artifacts found. Run packaging first or pass explicit artifact paths; "
            "use --allow-empty only for diagnostics.",
            file=sys.stderr,
        )
        return 2
    manifest = build_manifest(repo_root, artifacts)
    payload = json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(payload, encoding="utf-8")
    else:
        print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
