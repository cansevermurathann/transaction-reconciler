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

### Review individual differences

List the discrepancies for a saved run and record a note for one transaction.

```sh
python review.py review.sqlite3 differences 1
python review.py review.sqlite3 mark-difference-reviewed 1 T002 --note "Confirmed amount with provider"
python review.py review.sqlite3 differences 1
```

A transaction can be reviewed once per run. Reviews are stored alongside the
original report. Existing databases are supported, and run-level review status
is independent of transaction-level reviews.

Use `--status open` for the remaining review queue or `--status reviewed` to
see completed reviews. With no filter, the command returns all differences.
Listing runs or differences opens the database in read-only mode.

```sh
python review.py review.sqlite3 differences 1 --status open
```

## Continuous integration

GitHub Actions runs the unit and CLI integration tests on Linux and Windows
using Python 3.10 and 3.15. Pull requests to `main` and pushes to `main`
trigger the same test command used locally.

```sh
python -m unittest -v
```

## Retry a reconciliation batch

Supply a stable key for each logical batch when saving a report.

```sh
python reconcile.py examples/ledger.csv examples/settlement.csv --db review.sqlite3 --run-key batch-001
```

Repeating the same key with the same report returns the existing run ID and
preserves its reviews. Reusing a key with a different report returns exit code
2 and keeps the original run. The key identifies the report, so differences in
input files that leave the report unchanged do not cause a conflict.
Without a key, each save creates a new run.

### Export differences as CSV

```sh
python review.py review.sqlite3 differences 1 --status open --format csv > open-differences.csv
```

CSV includes transaction IDs, difference types, available amounts and
currencies, and review metadata. For spreadsheet display, the export prefixes
formula-like IDs and notes with an apostrophe. Use the default JSON output for
unmodified text or machine-to-machine exchange.
