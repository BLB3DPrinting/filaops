"""Tests for dependency-audit severity gating."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.ci import check_audit_severity


class AuditSeverityTests(unittest.TestCase):
    def run_report(self, kind: str, document: dict) -> int:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "audit.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            with patch("sys.argv", ["check_audit_severity.py", kind, str(path)]):
                return check_audit_severity.main(__import__("sys").argv)

    def test_pip_high_finding_blocks(self) -> None:
        report = {"vulnerabilities": [{"ratings": [{"severity": "high"}]}]}
        self.assertEqual(1, self.run_report("pip", report))

    def test_npm_medium_finding_does_not_block(self) -> None:
        report = {"vulnerabilities": {"example": {"severity": "moderate"}}}
        self.assertEqual(0, self.run_report("npm", report))

    def test_unclassified_finding_fails_closed(self) -> None:
        report = {"vulnerabilities": [{"ratings": [{}]}]}
        self.assertEqual(1, self.run_report("pip", report))

    def test_pip_finding_without_ratings_fails_closed(self) -> None:
        report = {"vulnerabilities": [{}]}
        self.assertEqual(1, self.run_report("pip", report))


if __name__ == "__main__":
    unittest.main()
