from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest


class ReviewWorkflowTests(unittest.TestCase):
    def test_reconciliation_can_be_saved_and_reviewed_once(self):
        root = Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / "review.sqlite3"

            def run(*args):
                return subprocess.run(
                    [sys.executable, *args], cwd=root, capture_output=True, text=True
                )

            result = run("reconcile.py", "examples/ledger.csv", "examples/settlement.csv",
                         "--db", str(db))
            self.assertEqual(result.returncode, 1, result.stderr)
            original = json.loads(result.stdout)
            listed = run("review.py", str(db), "list")
            self.assertEqual(listed.returncode, 0, listed.stderr)
            entry, = json.loads(listed.stdout)
            self.assertEqual(entry["report"], original)
            self.assertIsNone(entry["reviewed_at"])

            args = ("review.py", str(db), "mark-reviewed", str(entry["id"]), "--note")
            result = run(*args, "Checked export")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(run(*args, "Replace note").returncode, 2)
            reviewed, = json.loads(run("review.py", str(db), "list").stdout)
            self.assertEqual(reviewed["report"], original)
            self.assertEqual(reviewed["review_note"], "Checked export")
            self.assertIsNotNone(reviewed["reviewed_at"])
