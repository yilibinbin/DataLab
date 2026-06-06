from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from shared.update_signing import DEFAULT_UPDATE_SIGNING_KEY_ID, sign_manifest


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
    signing_private_key_b64: str | None = None,
    signing_key_id: str = DEFAULT_UPDATE_SIGNING_KEY_ID,
    allow_unsigned_assets: bool = False,
) -> dict[str, Any]:
    assets: dict[str, Any] = {}
    if macos_pkg is not None:
        assets["macos"] = _asset(Path(macos_pkg))
    if windows_exe is not None:
        assets["windows-x64"] = _asset(Path(windows_exe))

    manifest = {
        "schema_version": 1,
        "min_client_version": min_client_version,
        "version": version,
        "published_at": published_at,
        "release_url": release_url,
        "notes": notes,
        "assets": assets,
    }
    if signing_private_key_b64:
        return sign_manifest(
            manifest,
            private_key_b64=signing_private_key_b64,
            key_id=signing_key_id,
        )
    if assets and not allow_unsigned_assets:
        raise ValueError(
            "updates.json with installable assets must be signed; set "
            "DATALAB_UPDATE_SIGNING_PRIVATE_KEY_B64 or pass --allow-unsigned-assets "
            "for a manual-only/debug manifest"
        )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a DataLab updates.json manifest.")
    parser.add_argument("--version", required=True)
    parser.add_argument("--release-url", required=True)
    parser.add_argument("--notes-file", required=True)
    parser.add_argument("--published-at", required=True)
    parser.add_argument("--min-client-version", required=True)
    parser.add_argument("--macos-pkg")
    parser.add_argument("--windows-exe")
    parser.add_argument("--signing-private-key-b64")
    parser.add_argument("--signing-key-id")
    parser.add_argument("--allow-unsigned-assets", action="store_true")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    signing_private_key_b64 = (
        args.signing_private_key_b64
        or os.environ.get("DATALAB_UPDATE_SIGNING_PRIVATE_KEY_B64")
    )
    signing_key_id = (
        args.signing_key_id
        or os.environ.get("DATALAB_UPDATE_SIGNING_KEY_ID")
        or DEFAULT_UPDATE_SIGNING_KEY_ID
    )
    manifest = generate_manifest(
        version=args.version,
        release_url=args.release_url,
        notes=Path(args.notes_file).read_text(encoding="utf-8"),
        macos_pkg=Path(args.macos_pkg) if args.macos_pkg else None,
        windows_exe=Path(args.windows_exe) if args.windows_exe else None,
        published_at=args.published_at,
        min_client_version=args.min_client_version,
        signing_private_key_b64=signing_private_key_b64,
        signing_key_id=signing_key_id,
        allow_unsigned_assets=args.allow_unsigned_assets,
    )
    Path(args.output).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
