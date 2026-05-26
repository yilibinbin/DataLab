from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _asset(path: Path) -> dict[str, Any]:
    return {
        "name": path.name,
        "sha256": _sha256(path),
        "size_bytes": path.stat().st_size,
    }


def generate_manifest(
    *,
    version: str,
    release_url: str,
    notes: str,
    macos_pkg: Path | None,
    windows_exe: Path | None,
    published_at: str,
    min_client_version: str,
) -> dict[str, Any]:
    assets: dict[str, Any] = {}
    if macos_pkg is not None:
        assets["macos"] = _asset(Path(macos_pkg))
    if windows_exe is not None:
        assets["windows-x64"] = _asset(Path(windows_exe))

    return {
        "schema_version": 1,
        "min_client_version": min_client_version,
        "version": version,
        "published_at": published_at,
        "release_url": release_url,
        "notes": notes,
        "assets": assets,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a DataLab updates.json manifest.")
    parser.add_argument("--version", required=True)
    parser.add_argument("--release-url", required=True)
    parser.add_argument("--notes-file", required=True)
    parser.add_argument("--published-at", required=True)
    parser.add_argument("--min-client-version", required=True)
    parser.add_argument("--macos-pkg")
    parser.add_argument("--windows-exe")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    manifest = generate_manifest(
        version=args.version,
        release_url=args.release_url,
        notes=Path(args.notes_file).read_text(encoding="utf-8"),
        macos_pkg=Path(args.macos_pkg) if args.macos_pkg else None,
        windows_exe=Path(args.windows_exe) if args.windows_exe else None,
        published_at=args.published_at,
        min_client_version=args.min_client_version,
    )
    Path(args.output).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
