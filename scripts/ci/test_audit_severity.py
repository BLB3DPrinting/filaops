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

    def run_report_output(self, kind: str, document: dict) -> tuple[int, str]:
        import contextlib
        import io

        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = self.run_report(kind, document)
        return code, buffer.getvalue()

    def test_pip_findings_name_the_package(self) -> None:
        # Shape of a real pip-audit --format cyclonedx-json report: no ratings,
        # and the package is reached through the affects bom-ref.
        report = {
            "components": [
                {"bom-ref": "BomRef.1", "name": "requests", "version": "2.19.0"},
                {"bom-ref": "BomRef.2", "name": "certifi", "version": "2026.7.22"},
            ],
            "vulnerabilities": [
                {
                    "id": "PYSEC-2018-28",
                    "affects": [{"ref": "BomRef.1"}],
                    "recommendation": "Upgrade",
                }
            ],
        }
        code, output = self.run_report_output("pip", report)
        self.assertEqual(1, code)  # unrated, so it still fails closed
        self.assertIn("  PYSEC-2018-28: requests 2.19.0\n", output)
        self.assertIn("pip audit: 1 finding(s)", output)

    def test_pip_finding_with_unknown_ref_still_reports(self) -> None:
        report = {"vulnerabilities": [{"id": "GHSA-xxxx", "affects": [{"ref": "BomRef.9"}]}]}
        code, output = self.run_report_output("pip", report)
        self.assertEqual(1, code)
        self.assertIn("GHSA-xxxx: BomRef.9", output)

    def test_npm_findings_name_the_package(self) -> None:
        report = {"vulnerabilities": {"source-map-js": {"severity": "high", "range": "<1.2.2"}}}
        code, output = self.run_report_output("npm", report)
        self.assertEqual(1, code)
        self.assertIn("source-map-js: high (<1.2.2)", output)

    def test_clean_report_prints_no_findings(self) -> None:
        code, output = self.run_report_output("pip", {"components": [], "vulnerabilities": []})
        self.assertEqual(0, code)
        self.assertEqual("pip audit: 0 finding(s); blocking=[]; informational=[]; unknown=0\n", output)


if __name__ == "__main__":
    unittest.main()
