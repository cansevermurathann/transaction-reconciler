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

    def test_difference_review_supports_existing_databases(self):
        from contextlib import closing
        import sqlite3

        from review import list_differences, mark_difference_reviewed, save_run

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "legacy.sqlite3"
            report = {
                "matched": 1,
                "missing_from_settlement": ["T003"],
                "missing_from_ledger": ["T004"],
                "mismatched": [{"transaction_id": "T002", "ledger": {"amount": "125.45"}}],
            }
            run_id = save_run(path, report)
            with closing(sqlite3.connect(path)) as db, db:
                self.assertEqual(len(list_differences(db, run_id)), 3)
                with self.assertRaises(ValueError):
                    mark_difference_reviewed(db, run_id, "T001", "Matched")
                mark_difference_reviewed(db, run_id, "T002", "Checked")
                with self.assertRaises(ValueError):
                    mark_difference_reviewed(db, run_id, "T002", "Replacement")
            with closing(sqlite3.connect(path)) as db:
                items = {item["transaction_id"]: item for item in list_differences(db, run_id)}
                self.assertEqual(items["T002"]["review_note"], "Checked")
                self.assertEqual(items["T002"]["ledger"]["amount"], "125.45")
                self.assertIsNone(items["T003"]["reviewed_at"])
                self.assertIsNone(items["T004"]["reviewed_at"])

    def test_difference_queue_filters_saved_reviews(self):
        from review import save_run

        root = Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "queue.sqlite3"
            run_id = save_run(path, {
                "matched": 0,
                "missing_from_settlement": ["T001", "T002"],
                "missing_from_ledger": [],
                "mismatched": [],
            })

            def cli(*args):
                result = subprocess.run(
                    [sys.executable, "review.py", str(path), *args],
                    cwd=root, capture_output=True, text=True,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                return result.stdout

            def ids(status):
                output = cli("differences", str(run_id), "--status", status)
                return [item["transaction_id"] for item in json.loads(output)]

            original = path.read_bytes()
            self.assertEqual(ids("open"), ["T001", "T002"])
            self.assertEqual(ids("reviewed"), [])
            self.assertEqual(path.read_bytes(), original)

            cli("mark-difference-reviewed", str(run_id), "T001", "--note", "Checked")
            self.assertEqual(ids("all"), ["T001", "T002"])
            self.assertEqual(ids("open"), ["T002"])
            self.assertEqual(ids("reviewed"), ["T001"])

    def test_batch_key_reuses_run_and_rejects_conflicting_report(self):
        import sqlite3
        from contextlib import closing

        from review import list_runs, mark_reviewed, save_run

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "batches.sqlite3"
            report = {"matched": 1}
            first = save_run(path, report)
            keyed = save_run(path, report, "batch-001")
            with closing(sqlite3.connect(path)) as db, db:
                mark_reviewed(db, keyed, "Checked")
            self.assertEqual(save_run(path, report, "batch-001"), keyed)
            with self.assertRaisesRegex(ValueError, "different reconciliation report"):
                save_run(path, {"matched": 2}, "batch-001")
            with closing(sqlite3.connect(path)) as db:
                self.assertEqual([run["id"] for run in list_runs(db)], [keyed, first])
                self.assertEqual(list_runs(db)[0]["review_note"], "Checked")
