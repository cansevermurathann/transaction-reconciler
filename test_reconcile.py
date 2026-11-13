import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from reconcile import main, read_transactions


class ReconciliationTests(unittest.TestCase):
    def run_cli(self, ledger, settlement):
        output, errors = io.StringIO(), io.StringIO()
        with patch("sys.argv", ["reconcile.py", str(ledger), str(settlement)]):
            with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
                status = main()
        return status, output.getvalue(), errors.getvalue()

    def test_sample_reports_all_difference_types(self):
        root = Path(__file__).parent / "examples"
        status, output, _ = self.run_cli(root / "ledger.csv", root / "settlement.csv")
        report = json.loads(output)
        self.assertEqual(status, 1)
        self.assertEqual(report["matched"], 1)
        self.assertEqual(report["missing_from_settlement"], ["T003"])
        self.assertEqual(report["missing_from_ledger"], ["T004"])
        self.assertEqual(report["mismatched"], [{
            "transaction_id": "T002",
            "ledger": {"amount": "125.45", "currency": "TRY"},
            "settlement": {"amount": "125.40", "currency": "TRY"},
        }])

    def test_identical_files_exit_zero(self):
        ledger = Path(__file__).parent / "examples" / "ledger.csv"
        status, output, _ = self.run_cli(ledger, ledger)
        self.assertEqual(status, 0)
        self.assertEqual(json.loads(output)["matched"], 3)

    def test_invalid_input_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.csv"
            for rows in ("T1,NaN,TRY\n", "T1,1,TRY\nT1,2,TRY\n", "T1,1\n"):
                with self.subTest(rows=rows):
                    path.write_text("transaction_id,amount,currency\n" + rows, encoding="utf-8")
                    with self.assertRaises(ValueError):
                        read_transactions(path)
            status, output, errors = self.run_cli(path, path)
            self.assertEqual(status, 2)
            self.assertEqual(output, "")
            self.assertIn("wrong number of fields", errors)
