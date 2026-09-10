"""Regression tests for repository guardrail wording."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
FORBIDDEN_BYPASS_TEXT = "--" + "no-verify"
POLICY_FILES = (
    ROOT / ".githooks" / "pre-push",
    ROOT / "AGENT_POLICY.md",
    ROOT / "AGENTS.md",
    ROOT / ".claude" / "CLAUDE.md",
)


class GuardrailPolicyTests(unittest.TestCase):
    def test_guardrail_files_do_not_teach_hook_bypass(self) -> None:
        offenders = [
            str(path.relative_to(ROOT))
            for path in POLICY_FILES
            if FORBIDDEN_BYPASS_TEXT in path.read_text(encoding="utf-8")
        ]
        self.assertEqual([], offenders, f"bypass guidance found in: {offenders}")

    def test_policy_names_credential_and_approval_boundaries(self) -> None:
        policy = (ROOT / "AGENT_POLICY.md").read_text(encoding="utf-8")
        self.assertIn("Approval prompts and agent instructions are advisory", policy)
        self.assertIn("repository-scoped bot or GitHub App identities", policy)
        self.assertIn("never inherit administrator credentials", policy)
        self.assertIn("credential-helper access", policy)


if __name__ == "__main__":
    unittest.main()
