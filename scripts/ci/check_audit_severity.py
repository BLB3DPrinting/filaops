"""Apply the repository's high/critical dependency-audit merge policy."""

from __future__ import annotations

import json
import sys
from pathlib import Path


BLOCKING = {"high", "critical"}


def pip_severities(document: dict) -> list[str | None]:
    severities: list[str | None] = []
    for vulnerability in document.get("vulnerabilities", []):
        ratings = vulnerability.get("ratings") or []
        if not ratings:
            severities.append(None)
            continue
        severities.extend(rating.get("severity", "").lower() or None for rating in ratings)
    return severities


def npm_severities(document: dict) -> list[str | None]:
    return [
        (entry.get("severity") or "").lower() or None
        for entry in (document.get("vulnerabilities") or {}).values()
    ]


def main(argv: list[str]) -> int:
    if len(argv) != 3 or argv[1] not in {"pip", "npm"}:
        print("usage: check_audit_severity.py pip|npm REPORT.json", file=sys.stderr)
        return 2

    kind = argv[1]
    report_path = Path(argv[2])
    try:
        document = json.loads(report_path.read_text(encoding="utf-8"))
        severities = pip_severities(document) if kind == "pip" else npm_severities(document)
    except (OSError, json.JSONDecodeError, AttributeError, TypeError) as error:
        print(f"dependency audit report is invalid: {error}", file=sys.stderr)
        return 2

    unknown = sum(severity is None for severity in severities)
    blocking = sorted({severity for severity in severities if severity in BLOCKING})
    informational = sorted({severity for severity in severities if severity not in BLOCKING and severity})

    print(f"{kind} audit: {len(severities)} finding(s); blocking={blocking}; informational={informational}; unknown={unknown}")
    if unknown:
        print("dependency audit contains unclassified findings; failing closed", file=sys.stderr)
        return 1
    return 1 if blocking else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
