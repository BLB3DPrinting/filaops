"""Unit tests for the pure parts of scripts/ci/ai_review.py (no network)."""

import unittest
from types import SimpleNamespace

from scripts.ci import ai_review as r

DIFF = """diff --git a/backend/app/services/foo.py b/backend/app/services/foo.py
index 1111111..2222222 100644
--- a/backend/app/services/foo.py
+++ b/backend/app/services/foo.py
@@ -10,4 +10,5 @@ def total(q):
     a = 1
-    b = 2
+    b = 3
+    c = 4
     return a + b
diff --git a/docs/notes.md b/docs/notes.md
new file mode 100644
--- /dev/null
+++ b/docs/notes.md
@@ -0,0 +1,2 @@
+# Notes
+hello
diff --git a/frontend/package-lock.json b/frontend/package-lock.json
--- a/frontend/package-lock.json
+++ b/frontend/package-lock.json
@@ -1,1 +1,1 @@
-{"a": 1}
+{"a": 2}
diff --git a/backend/old.py b/backend/old.py
deleted file mode 100644
--- a/backend/old.py
+++ /dev/null
@@ -1,1 +0,0 @@
-x = 1
diff --git a/img/logo.png b/img/logo.png
Binary files a/img/logo.png and b/img/logo.png differ
"""


def finding(**kw):
    base = {
        "severity": "major",
        "category": "correctness",
        "path": "backend/app/services/foo.py",
        "line": 11,
        "title": "Wrong total",
        "body": "b changed.",
        "suggested_fix": "Use 2.",
    }
    base.update(kw)
    return base


class SplitDiffTests(unittest.TestCase):
    def setUp(self):
        self.files = {f.path: f for f in r.split_diff(DIFF)}

    def test_paths(self):
        self.assertEqual(
            set(self.files),
            {"backend/app/services/foo.py", "docs/notes.md", "frontend/package-lock.json", "backend/old.py", "img/logo.png"},
        )

    def test_new_file_line_numbers_and_commentable_lines(self):
        foo = self.files["backend/app/services/foo.py"]
        self.assertEqual(foo.commentable, {10, 11, 12, 13})
        self.assertIn("   11 +    b = 3", foo.annotated)
        self.assertIn("   13      return a + b", foo.annotated)
        self.assertIn("      -    b = 2", foo.annotated)

    def test_deleted_file_has_no_commentable_lines(self):
        self.assertEqual(self.files["backend/old.py"].commentable, set())

    def test_binary_detected(self):
        self.assertTrue(self.files["img/logo.png"].binary)


class SelectionTests(unittest.TestCase):
    def test_excludes_lockfiles_and_binaries(self):
        chosen, excluded, over = r.select_files(r.split_diff(DIFF), 100_000)
        self.assertEqual(set(excluded), {"frontend/package-lock.json", "img/logo.png"})
        self.assertEqual(over, [])
        self.assertEqual(chosen[-1].path, "docs/notes.md")  # docs sorted last

    def test_size_cap_drops_docs_first(self):
        files = r.split_diff(DIFF)
        code = [f for f in files if f.path == "backend/app/services/foo.py"][0]
        cap = len(code.annotated) + len(code.path) + 16 + 60
        chosen, _, over = r.select_files(files, cap)
        self.assertIn("backend/app/services/foo.py", [f.path for f in chosen])
        self.assertIn("docs/notes.md", over)

    def test_docs_detection(self):
        self.assertTrue(r.is_docs("docs/reports/x.md"))
        self.assertTrue(r.is_docs("README.md"))
        self.assertFalse(r.is_docs("backend/app/main.py"))

    def test_fingerprint_changes_with_diff_and_model(self):
        files = r.split_diff(DIFF)
        a = r.diff_fingerprint(files, "m1", "p")
        self.assertEqual(a, r.diff_fingerprint(r.split_diff(DIFF), "m1", "p"))
        self.assertNotEqual(a, r.diff_fingerprint(files, "m2", "p"))
        self.assertNotEqual(a, r.diff_fingerprint(files[:1], "m1", "p"))


class FindingTests(unittest.TestCase):
    def test_blocking_threshold(self):
        self.assertTrue(r.is_blocking("critical", "major"))
        self.assertTrue(r.is_blocking("major", "major"))
        self.assertFalse(r.is_blocking("minor", "major"))
        self.assertFalse(r.is_blocking("major", "critical"))
        self.assertFalse(r.is_blocking("critical", "none"))

    def test_place_findings(self):
        files = r.split_diff(DIFF)
        on_line = finding()
        off_line = finding(line=50)
        other_file = finding(path="backend/app/other.py")
        whole = finding(line=0)
        inline, general = r.place_findings([on_line, off_line, other_file, whole], files)
        self.assertEqual(inline, [on_line])
        self.assertEqual(general, [off_line, other_file, whole])

    def test_fingerprint_ignores_case_and_punctuation(self):
        self.assertEqual(
            r.finding_fingerprint(finding(title="Wrong total!")),
            r.finding_fingerprint(finding(title="wrong  TOTAL")),
        )

    def test_validate_finding_normalises_bad_values(self):
        clean = r.validate_finding({"severity": "huge", "path": "/a.py", "line": "7", "title": ""})
        self.assertEqual(clean["severity"], "minor")
        self.assertEqual(clean["path"], "a.py")
        self.assertEqual(clean["line"], 0)
        self.assertEqual(clean["title"], "Untitled finding")

    def test_inline_body_carries_marker_and_blocking(self):
        body = r.inline_body(finding(), "claude-opus-5-5", "major")
        self.assertIn("[MAJOR] correctness: Wrong total", body)
        self.assertIn("blocking", body)
        self.assertRegex(body, r.FINDING_FP_RE)

    def test_summary_round_trips_state(self):
        state = {"diff": "abc", "head": "deadbeef", "blocking": 1}
        body = r.summary_body(
            model="claude-opus-5-5",
            head_sha="deadbeefcafe",
            result={"summary": "Risky."},
            inline=[finding()],
            general=[finding(line=0, severity="nit", title="Pipe | title")],
            fail_on="major",
            excluded=["x.png"],
            over_cap=[],
            cost_line="Tokens: 1 in, 1 out.",
            state=state,
        )
        self.assertIn(r.SUMMARY_MARKER, body)
        self.assertIn("1 blocking finding", body)
        self.assertIn("Pipe \\| title", body)
        self.assertEqual(r.parse_state(body), state)
        self.assertIsNone(r.parse_state("no marker"))

    def test_cost_line(self):
        usage = SimpleNamespace(input_tokens=1_000_000, output_tokens=100_000)
        self.assertIn("$6.000", r.cost_line("claude-opus-5-5", usage))
        self.assertNotIn("$", r.cost_line("unknown-model", usage))


if __name__ == "__main__":
    unittest.main()
