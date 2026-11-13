"""Compare two transaction exports using exact decimal amounts."""

import argparse
import csv
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import sys
import sqlite3

from review import save_run

COLUMNS = {"transaction_id", "amount", "currency"}


def read_transactions(path):
    transactions = {}
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream, strict=True)
        headers = reader.fieldnames or []
        if len(set(headers)) != len(headers) or not COLUMNS.issubset(headers):
            raise ValueError(f"{path}: expected unique headers including {', '.join(sorted(COLUMNS))}")
        for row in reader:
            location = f"{path}:{reader.line_num}"
            if None in row or any(value is None for value in row.values()):
                raise ValueError(f"{location}: wrong number of fields")
            transaction_id = row["transaction_id"].strip()
            currency = row["currency"].strip().upper()
            if not transaction_id or transaction_id in transactions:
                raise ValueError(f"{location}: blank or duplicate transaction ID")
            if len(currency) != 3 or not currency.isascii() or not currency.isalpha():
                raise ValueError(f"{location}: expected a three-letter currency code")
            try:
                amount = Decimal(row["amount"].strip())
            except InvalidOperation as error:
                raise ValueError(f"{location}: invalid amount") from error
            if not amount.is_finite():
                raise ValueError(f"{location}: amount must be finite")
            transactions[transaction_id] = (amount, currency)
    return transactions


def describe(transaction):
    amount, currency = transaction
    return {"amount": str(amount), "currency": currency}


def reconcile(ledger, settlement):
    report = {"matched": 0, "missing_from_settlement": [], "missing_from_ledger": [], "mismatched": []}
    for transaction_id in sorted(ledger.keys() | settlement.keys()):
        if transaction_id not in settlement:
            report["missing_from_settlement"].append(transaction_id)
        elif transaction_id not in ledger:
            report["missing_from_ledger"].append(transaction_id)
        elif ledger[transaction_id] == settlement[transaction_id]:
            report["matched"] += 1
        else:
            report["mismatched"].append({
                "transaction_id": transaction_id,
                "ledger": describe(ledger[transaction_id]),
                "settlement": describe(settlement[transaction_id]),
            })
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ledger", type=Path)
    parser.add_argument("settlement", type=Path)
    parser.add_argument("--db", type=Path, help="save the report to a review database")
    args = parser.parse_args()
    try:
        report = reconcile(read_transactions(args.ledger), read_transactions(args.settlement))
        if args.db is not None:
            run_id = save_run(args.db, report)
            print(f"Saved run {run_id}", file=sys.stderr)
    except (OSError, ValueError, csv.Error, sqlite3.Error) as error:
        print(error, file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2))
    return int(any(report[key] for key in ("missing_from_settlement", "missing_from_ledger", "mismatched")))


if __name__ == "__main__":
    sys.exit(main())
