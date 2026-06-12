#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app_desktop.webengine_spike_assets import (  # noqa: E402
    build_asset_evidence_template,
    build_materialized_asset_manifest,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create DataLab WebEngine offline asset evidence JSON.")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd(), help="Repository root.")
    parser.add_argument("--template", action="store_true", help="Write a missing-assets template instead of hashing files.")
    parser.add_argument("--generated-at", help="Timestamp to use in output.")
    parser.add_argument("--out", type=Path, help="Optional JSON output path.")
    args = parser.parse_args(argv)

    if args.template:
        payload = build_asset_evidence_template(generated_at=args.generated_at)
    else:
        payload = build_materialized_asset_manifest(args.repo_root, generated_at=args.generated_at)

    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
