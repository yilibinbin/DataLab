#!/usr/bin/env python3
from __future__ import annotations

import argparse
import plistlib
from pathlib import Path


def inspect_bundle(app_path: Path) -> list[str]:
    issues: list[str] = []
    plist_path = app_path / "Contents" / "Info.plist"
    resources_path = app_path / "Contents" / "Resources"

    if not app_path.exists():
        return [f"missing app bundle: {app_path}"]
    if not app_path.is_dir():
        return [f"app bundle path is not a directory: {app_path}"]
    if not plist_path.is_file():
        return [f"missing Info.plist: {plist_path}"]

    try:
        data = plistlib.loads(plist_path.read_bytes())
    except Exception as exc:
        return [f"could not read Info.plist: {plist_path}: {exc}"]

    if not isinstance(data, dict):
        return ["Info.plist root is not a dictionary"]

    icon_name = str(data.get("CFBundleIconFile") or "").strip()
    if not icon_name:
        issues.append("missing CFBundleIconFile in Contents/Info.plist")
        return issues

    icon_file = icon_name if icon_name.endswith(".icns") else f"{icon_name}.icns"
    icon_path = resources_path / icon_file
    if not icon_path.is_file():
        issues.append(f"missing icon resource: Contents/Resources/{icon_file}")

    return issues


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify macOS .app bundle icon plist metadata and resource file."
    )
    parser.add_argument("app", type=Path, help="Path to a .app bundle")
    args = parser.parse_args()

    issues = inspect_bundle(args.app)
    if issues:
        print("macOS bundle icon metadata issues:")
        for issue in issues:
            print(f"- {issue}")
        return 1

    print("macOS bundle icon metadata OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
