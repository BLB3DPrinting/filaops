#!/usr/bin/env python3
"""Fail when FilaOps runtime or lockfile version metadata drifts."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


SEMVER = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)


def _load_json(root: Path, relative_path: str, errors: list[str]) -> dict[str, Any]:
    path = root / relative_path
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"{relative_path}: cannot read valid JSON ({exc})")
        return {}
    if not isinstance(value, dict):
        errors.append(f"{relative_path}: root value must be an object")
        return {}
    return value


def _record_string(
    values: dict[str, str], label: str, value: Any, errors: list[str]
) -> None:
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{label}: expected a non-empty string")
        return
    values[label] = value.strip()


def _lockfile_root_package(
    lockfile: dict[str, Any], label: str, errors: list[str]
) -> dict[str, Any]:
    packages = lockfile.get("packages")
    if not isinstance(packages, dict):
        errors.append(f"{label}: packages must be an object")
        return {}
    root_package = packages.get("")
    if not isinstance(root_package, dict):
        errors.append(f'{label}: packages[""] must be an object')
        return {}
    return root_package


def validate_repository(root: Path) -> list[str]:
    """Return all version and derived lockfile metadata errors under *root*."""

    root = root.resolve()
    errors: list[str] = []
    versions: dict[str, str] = {}
    names: dict[str, str] = {}

    try:
        backend_version = (root / "backend" / "VERSION").read_text(encoding="utf-8")
    except OSError as exc:
        errors.append(f"backend/VERSION: cannot read ({exc})")
    else:
        _record_string(versions, "backend/VERSION", backend_version, errors)

    root_package = _load_json(root, "package.json", errors)
    root_lock = _load_json(root, "package-lock.json", errors)
    frontend_package = _load_json(root, "frontend/package.json", errors)
    frontend_lock = _load_json(root, "frontend/package-lock.json", errors)

    root_lock_package = _lockfile_root_package(root_lock, "package-lock.json", errors)
    frontend_lock_package = _lockfile_root_package(
        frontend_lock, "frontend/package-lock.json", errors
    )

    version_fields = (
        ("package.json", root_package.get("version")),
        ("package-lock.json", root_lock.get("version")),
        ('package-lock.json packages[""]', root_lock_package.get("version")),
        ("frontend/package.json", frontend_package.get("version")),
        ("frontend/package-lock.json", frontend_lock.get("version")),
        (
            'frontend/package-lock.json packages[""]',
            frontend_lock_package.get("version"),
        ),
    )
    for label, value in version_fields:
        _record_string(versions, label, value, errors)

    name_fields = (
        ("package.json", root_package.get("name")),
        ("package-lock.json", root_lock.get("name")),
        ('package-lock.json packages[""]', root_lock_package.get("name")),
        ("frontend/package.json", frontend_package.get("name")),
        ("frontend/package-lock.json", frontend_lock.get("name")),
        (
            'frontend/package-lock.json packages[""]',
            frontend_lock_package.get("name"),
        ),
    )
    for label, value in name_fields:
        _record_string(names, label, value, errors)

    for label, version in versions.items():
        if not SEMVER.fullmatch(version):
            errors.append(f"{label}: {version!r} is not a valid semantic version")

    if len(set(versions.values())) > 1:
        rendered = ", ".join(f"{label}={value}" for label, value in versions.items())
        errors.append(f"version sources disagree: {rendered}")

    name_groups = (
        (
            "root",
            names.get("package.json"),
            names.get("package-lock.json"),
            names.get('package-lock.json packages[""]'),
        ),
        (
            "frontend",
            names.get("frontend/package.json"),
            names.get("frontend/package-lock.json"),
            names.get('frontend/package-lock.json packages[""]'),
        ),
    )
    for group, *group_names in name_groups:
        present_names = [name for name in group_names if name is not None]
        if len(set(present_names)) > 1:
            errors.append(f"{group} package names disagree: {', '.join(present_names)}")

    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
        help="repository root (defaults to the script's repository)",
    )
    args = parser.parse_args(argv)
    errors = validate_repository(args.root)
    if errors:
        print("Version parity check failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    version = (args.root / "backend" / "VERSION").read_text(encoding="utf-8").strip()
    print(f"Version parity check passed: {version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
