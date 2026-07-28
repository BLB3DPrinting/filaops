from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.ci.check_version_parity import validate_repository


class VersionParityTests(unittest.TestCase):
    def make_repository(self, version: str = "4.2.0-rc.1") -> Path:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        (root / "backend").mkdir()
        (root / "frontend").mkdir()
        (root / "backend" / "VERSION").write_text(version, encoding="utf-8")
        self.write_json(root / "package.json", {"name": "filaops", "version": version})
        self.write_json(
            root / "package-lock.json",
            {
                "name": "filaops",
                "version": version,
                "packages": {"": {"name": "filaops", "version": version}},
            },
        )
        self.write_json(
            root / "frontend" / "package.json",
            {"name": "frontend", "version": version},
        )
        self.write_json(
            root / "frontend" / "package-lock.json",
            {
                "name": "frontend",
                "version": version,
                "packages": {"": {"name": "frontend", "version": version}},
            },
        )
        return root

    @staticmethod
    def write_json(path: Path, value: dict[str, object]) -> None:
        path.write_text(json.dumps(value), encoding="utf-8")

    def test_accepts_matching_prerelease(self) -> None:
        self.assertEqual(validate_repository(self.make_repository()), [])

    def test_accepts_backend_version_file_newline(self) -> None:
        root = self.make_repository()
        (root / "backend" / "VERSION").write_text("4.2.0-rc.1\n", encoding="utf-8")

        self.assertEqual(validate_repository(root), [])

    def test_rejects_stale_lockfile_version(self) -> None:
        root = self.make_repository()
        lock_path = root / "frontend" / "package-lock.json"
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
        lock["packages"][""]["version"] = "4.1.0"
        self.write_json(lock_path, lock)

        errors = validate_repository(root)

        self.assertTrue(any("version sources disagree" in error for error in errors))

    def test_rejects_stale_lockfile_name(self) -> None:
        root = self.make_repository()
        lock_path = root / "package-lock.json"
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
        lock["name"] = "blb3d-erp"
        self.write_json(lock_path, lock)

        errors = validate_repository(root)

        self.assertTrue(any("root package names disagree" in error for error in errors))

    def test_rejects_invalid_lockfile_root_metadata(self) -> None:
        root = self.make_repository()
        lock_path = root / "package-lock.json"
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
        lock["packages"] = []
        self.write_json(lock_path, lock)

        errors = validate_repository(root)

        self.assertIn("package-lock.json: packages must be an object", errors)

    def test_rejects_invalid_semver(self) -> None:
        root = self.make_repository("release-4.2")

        errors = validate_repository(root)

        self.assertTrue(
            any("not a valid semantic version" in error for error in errors)
        )

    def test_rejects_numeric_prerelease_with_leading_zero(self) -> None:
        root = self.make_repository("4.2.0-01")

        errors = validate_repository(root)

        self.assertTrue(
            any("not a valid semantic version" in error for error in errors)
        )

    def test_rejects_whitespace_in_json_metadata(self) -> None:
        root = self.make_repository()
        package_path = root / "package.json"
        package = json.loads(package_path.read_text(encoding="utf-8"))
        package["version"] = " 4.2.0-rc.1"
        self.write_json(package_path, package)

        errors = validate_repository(root)

        self.assertIn(
            "package.json: must not contain leading or trailing whitespace", errors
        )


if __name__ == "__main__":
    unittest.main()
