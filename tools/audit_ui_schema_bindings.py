from __future__ import annotations

import argparse
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path


MIGRATED_BIND_MARKERS = (
    "bind_field(",
    "bind_choices(",
    "register_schema_text_refresh(",
    "_register_schema_text_refresh(",
    "bind_schema_command_button(",
    "_bind_schema_command_button(",
)
MANUAL_TEXT_MARKERS = (
    ".setToolTip(",
    ".setPlaceholderText(",
    "._register_text(",
    "self._register_text(",
)
ALLOWLIST_SNIPPETS = (
    "register_schema_text_refresh(",
    "_register_schema_text_refresh(",
    "bind_schema_command_button(",
    "_bind_schema_command_button(",
    "setAccessibleName",
    "setAccessibleDescription",
)


@dataclass(frozen=True, order=True)
class AuditFinding:
    filename: str
    line: int
    code: str
    detail: str


def _finding_key(finding: AuditFinding) -> str:
    return f"{finding.filename}:{finding.line}:{finding.code}"


def audit_source_text(
    source: str,
    *,
    filename: str,
    allowlist: set[str] | None = None,
) -> list[AuditFinding]:
    allowlist = allowlist or set()
    findings: list[AuditFinding] = []
    in_migrated_binding_block = False
    for line_number, line in enumerate(source.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("def _bind_") and "schema" in stripped:
            in_migrated_binding_block = True
        elif stripped.startswith("def ") and not stripped.startswith("def _bind_"):
            in_migrated_binding_block = False

        if not stripped.startswith("def ") and any(marker in stripped for marker in MIGRATED_BIND_MARKERS):
            in_migrated_binding_block = True

        if not in_migrated_binding_block:
            continue
        if any(snippet in stripped for snippet in ALLOWLIST_SNIPPETS):
            continue
        if any(marker in stripped for marker in MANUAL_TEXT_MARKERS):
            finding = AuditFinding(
                filename=filename,
                line=line_number,
                code="manual-tooltip-after-schema-bind",
                detail=stripped,
            )
            if _finding_key(finding) not in allowlist:
                findings.append(finding)
    return sorted(findings)


def read_allowlist(path: Path | None) -> set[str]:
    if path is None or not path.exists():
        return set()
    return {
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }


def audit_paths(
    paths: Iterable[Path],
    *,
    allowlist: set[str] | None = None,
) -> list[AuditFinding]:
    findings: list[AuditFinding] = []
    for path in paths:
        findings.extend(
            audit_source_text(
                path.read_text(encoding="utf-8"),
                filename=str(path),
                allowlist=allowlist,
            )
        )
    return sorted(findings)


def format_findings(findings: Iterable[AuditFinding]) -> str:
    return "\n".join(
        f"{finding.filename}:{finding.line}: {finding.code}: {finding.detail}"
        for finding in sorted(findings)
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--migrated-only", action="store_true")
    parser.add_argument(
        "--allowlist",
        type=Path,
        default=Path("tools/ui_schema_audit_allowlist.txt"),
    )
    parser.add_argument("paths", nargs="*", default=["app_desktop/panels.py"])
    args = parser.parse_args()

    findings = audit_paths(
        (Path(path) for path in args.paths),
        allowlist=read_allowlist(args.allowlist),
    )
    if findings:
        print(format_findings(findings))
        return 1
    print("No schema audit findings.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
