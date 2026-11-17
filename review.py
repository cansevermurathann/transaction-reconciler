"""List saved reconciliation runs and record reviews in a local SQLite database."""

import argparse
from contextlib import closing
import csv
import json
from pathlib import Path
import sqlite3
import sys


def save_run(path, report, run_key=None):
    with closing(sqlite3.connect(path)) as db, db:
        db.execute("PRAGMA foreign_keys = ON")
        db.execute("BEGIN IMMEDIATE")
        db.execute("""
            CREATE TABLE IF NOT EXISTS runs (
                id INTEGER PRIMARY KEY,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                report TEXT NOT NULL,
                reviewed_at TEXT,
                review_note TEXT
            )
        """)
        if run_key is not None:
            db.execute("""
                CREATE TABLE IF NOT EXISTS run_keys (
                    key TEXT PRIMARY KEY,
                    run_id INTEGER NOT NULL REFERENCES runs(id)
                )
            """)
            existing = db.execute("""
                SELECT runs.id, runs.report FROM run_keys
                JOIN runs ON runs.id = run_keys.run_id WHERE run_keys.key = ?
            """, (run_key,)).fetchone()
            if existing is not None:
                if json.loads(existing[1]) != report:
                    raise ValueError("Run key already exists with a different reconciliation report.")
                return existing[0]

        cursor = db.execute("INSERT INTO runs (report) VALUES (?)", (json.dumps(report),))
        run_id = cursor.lastrowid
        if run_key is not None:
            db.execute("INSERT INTO run_keys (key, run_id) VALUES (?, ?)", (run_key, run_id))
        return run_id


def list_runs(db):
    rows = db.execute("""
        SELECT id, created_at, report, reviewed_at, review_note FROM runs ORDER BY id DESC
    """)
    return [
        {
            "id": row[0],
            "created_at": row[1],
            "report": json.loads(row[2]),
            "reviewed_at": row[3],
            "review_note": row[4],
        }
        for row in rows
    ]


def mark_reviewed(db, run_id, note):
    cursor = db.execute("""
        UPDATE runs
        SET reviewed_at = CURRENT_TIMESTAMP, review_note = ?
        WHERE id = ? AND reviewed_at IS NULL
    """, (note, run_id))
    if cursor.rowcount != 1:
        raise ValueError(f"Run {run_id} does not exist or has already been reviewed.")


def list_differences(db, run_id):
    row = db.execute("SELECT report FROM runs WHERE id = ?", (run_id,)).fetchone()
    if row is None:
        raise ValueError(f"Run {run_id} does not exist.")

    review_table = db.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'difference_reviews'"
    ).fetchone()
    review_rows = db.execute(
        "SELECT transaction_id, review_note, reviewed_at FROM difference_reviews WHERE run_id = ?",
        (run_id,),
    ) if review_table else ()
    reviews = {
        transaction_id: {"review_note": note, "reviewed_at": timestamp}
        for transaction_id, note, timestamp in review_rows
    }
    report = json.loads(row[0])
    differences = [
        {"transaction_id": transaction_id, "kind": kind}
        for kind in ("missing_from_settlement", "missing_from_ledger")
        for transaction_id in report[kind]
    ]
    differences.extend({"kind": "mismatched", **item} for item in report["mismatched"])
    for item in differences:
        item.update(reviews.get(item["transaction_id"], {"review_note": None, "reviewed_at": None}))
    return differences


def mark_difference_reviewed(db, run_id, transaction_id, note):
    if not any(item["transaction_id"] == transaction_id for item in list_differences(db, run_id)):
        raise ValueError(f"Transaction {transaction_id} is not a difference in run {run_id}.")
    db.execute("""
        CREATE TABLE IF NOT EXISTS difference_reviews (
            run_id INTEGER NOT NULL REFERENCES runs(id),
            transaction_id TEXT NOT NULL,
            review_note TEXT NOT NULL,
            reviewed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (run_id, transaction_id)
        )
    """)
    cursor = db.execute("""
        INSERT INTO difference_reviews (run_id, transaction_id, review_note)
        VALUES (?, ?, ?)
        ON CONFLICT (run_id, transaction_id) DO NOTHING
    """, (run_id, transaction_id, note))
    if cursor.rowcount != 1:
        raise ValueError(f"Transaction {transaction_id} has already been reviewed in run {run_id}.")


def spreadsheet_text(value):
    if value and (value.startswith(("\t", "\r", "\n")) or
                  value.lstrip().startswith(("=", "+", "-", "@", "＝", "＋", "－", "＠"))):
        return "'" + value
    return value


def write_differences_csv(items, stream):
    writer = csv.writer(stream, quoting=csv.QUOTE_ALL)
    writer.writerow([
        "transaction_id", "kind", "ledger_amount", "ledger_currency",
        "settlement_amount", "settlement_currency", "reviewed_at", "review_note",
    ])
    for item in items:
        ledger = item.get("ledger", {})
        settlement = item.get("settlement", {})
        writer.writerow([
            spreadsheet_text(item["transaction_id"]), item["kind"],
            ledger.get("amount"), ledger.get("currency"),
            settlement.get("amount"), settlement.get("currency"),
            item["reviewed_at"], spreadsheet_text(item["review_note"]),
        ])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("db", type=Path)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list")
    mark = commands.add_parser("mark-reviewed")
    mark.add_argument("run_id", type=int)
    mark.add_argument("--note", required=True)
    differences = commands.add_parser("differences")
    differences.add_argument("run_id", type=int)
    differences.add_argument("--status", choices=("all", "open", "reviewed"), default="all")
    differences.add_argument("--format", choices=("json", "csv"), default="json")
    mark_difference = commands.add_parser("mark-difference-reviewed")
    mark_difference.add_argument("run_id", type=int)
    mark_difference.add_argument("transaction_id")
    mark_difference.add_argument("--note", required=True)
    args = parser.parse_args()

    try:
        mode = "ro" if args.command in ("list", "differences") else "rw"
        with closing(sqlite3.connect(args.db.resolve().as_uri() + f"?mode={mode}", uri=True)) as db, db:
            db.execute("PRAGMA foreign_keys = ON")
            if args.command == "list":
                print(json.dumps(list_runs(db), indent=2))
            elif args.command == "differences":
                items = list_differences(db, args.run_id)
                if args.status != "all":
                    reviewed = args.status == "reviewed"
                    items = [item for item in items if (item["reviewed_at"] is not None) == reviewed]
                if args.format == "csv":
                    # csv controls line endings, including on Windows.
                    sys.stdout.reconfigure(newline="")
                    write_differences_csv(items, sys.stdout)
                else:
                    print(json.dumps(items, indent=2))
            else:
                note = args.note.strip()
                if not note:
                    raise ValueError("Enter a non-empty review note.")
                if args.command == "mark-reviewed":
                    mark_reviewed(db, args.run_id, note)
                else:
                    mark_difference_reviewed(db, args.run_id, args.transaction_id, note)
    except (sqlite3.Error, ValueError) as error:
        print(error, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
