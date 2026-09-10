"""Regression tests for repository and workflow guardrails."""

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"
FORBIDDEN_BYPASS_TEXT = "--" + "no-verify"


class WorkflowHardeningTests(unittest.TestCase):
    def test_all_actions_are_pinned_to_commit_shas(self) -> None:
        mutable = []
        for path in WORKFLOWS.glob("*.yml"):
            for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                match = re.search(r"\buses:\s*([^\s#]+)", line)
                if match and not re.fullmatch(r".+@[0-9a-f]{40}", match.group(1)):
                    mutable.append(f"{path.relative_to(ROOT)}:{line_number}")
        self.assertEqual([], mutable, f"mutable workflow actions found at: {mutable}")

    def test_bypass_guidance_is_absent(self) -> None:
        files = [ROOT / ".githooks" / "pre-push", ROOT / "AGENT_POLICY.md"]
        offenders = [str(path.relative_to(ROOT)) for path in files
                     if FORBIDDEN_BYPASS_TEXT in path.read_text(encoding="utf-8")]
        self.assertEqual([], offenders, f"bypass guidance found in: {offenders}")

    def test_security_workflows_run_for_pull_requests(self) -> None:
        for name in ("codeql.yml", "pro-guard.yml"):
            content = (WORKFLOWS / name).read_text(encoding="utf-8")
            self.assertRegex(content, r"(?m)^\s*pull_request:\s*$", name)

    def test_review_council_workflow_is_absent(self) -> None:
        self.assertFalse((WORKFLOWS / "review-council.yml").exists())

    def test_dependency_audit_is_in_core_ci(self) -> None:
        content = (WORKFLOWS / "core-ci.yml").read_text(encoding="utf-8")
        self.assertIn("core-dependency-audit:", content)
        self.assertIn("check_audit_severity.py", content)


if __name__ == "__main__":
    unittest.main()
