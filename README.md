# Transaction Reconciler

A Python command-line tool that compares an internal transaction ledger with a settlement export and reports records that need review. Both sample files contain synthetic data.

## Quick start

Requires Python 3.10 or newer. Uses only the standard library.

```sh
python reconcile.py examples/ledger.csv examples/settlement.csv
python -m unittest -v
```

The sample produces one match, one missing record on each side, and one amount mismatch.

## Input and output

Provide two UTF-8 CSV files with `transaction_id`, `amount`, and `currency` columns. IDs are case-sensitive and unique within each file. Amounts use decimal notation without thousands separators, and currency uses three letters. Negative amounts are supported. The tool compares by transaction ID and uses Python's `Decimal` to compare amounts without floating-point rounding. It flags currency differences as mismatches.

The JSON report is written to stdout. Invalid files are reported on stderr with a row number when applicable.

| Exit code | Meaning |
| --- | --- |
| 0 | All transactions match |
| 1 | Reconciliation differences found |
| 2 | Invalid input or unreadable file |

## Review workflow

Use `--db` to save a reconciliation run. Each run keeps its original JSON
report and a UTC creation timestamp. The command still prints the report to
stdout and returns exit code 1 when it finds differences.

```sh
python reconcile.py examples/ledger.csv examples/settlement.csv --db review.sqlite3
python review.py review.sqlite3 list
python review.py review.sqlite3 mark-reviewed 1 --note "Checked settlement against source export"
python review.py review.sqlite3 list
```

Use the ID shown by the list command when reviewing an existing database.
The review command records a note and UTC timestamp once per run. A review
records that someone inspected the differences. The original report stays
available for reference.
