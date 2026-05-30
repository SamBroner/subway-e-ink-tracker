import argparse
import csv
import os
import sqlite3
from pathlib import Path

from dotenv import load_dotenv


DEFAULT_TABLES = [
    "weather_observations",
    "bike_observations",
    "train_snapshots",
    "train_arrivals",
    "combined_observations",
]


def connect(db_path: Path) -> sqlite3.Connection:
    return sqlite3.connect(db_path)


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return row is not None


def table_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return [row[1] for row in rows]


def print_status(conn: sqlite3.Connection):
    page_count = conn.execute("PRAGMA page_count").fetchone()[0]
    page_size = conn.execute("PRAGMA page_size").fetchone()[0]
    db_size_mb = (page_count * page_size) / (1024 * 1024)
    print(f"db_size_mb: {db_size_mb:.2f}")

    for table in DEFAULT_TABLES:
        if not table_exists(conn, table):
            print(f"{table}: missing")
            continue

        total = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        has_observed = "observed_at_utc" in table_columns(conn, table)
        if has_observed and total:
            min_max = conn.execute(
                f"SELECT MIN(observed_at_utc), MAX(observed_at_utc) FROM {table}"
            ).fetchone()
            print(f"{table}: {total} rows ({min_max[0]} -> {min_max[1]})")
        else:
            print(f"{table}: {total} rows")


def export_table(
    conn: sqlite3.Connection,
    table: str,
    output_dir: Path,
    start_date: str | None = None,
    end_date: str | None = None,
):
    if not table_exists(conn, table):
        print(f"Skipping {table}: missing")
        return

    columns = table_columns(conn, table)
    query = f"SELECT * FROM {table}"
    params: list[str] = []
    where_parts: list[str] = []

    if "local_date" in columns and start_date:
        where_parts.append("local_date >= ?")
        params.append(start_date)
    if "local_date" in columns and end_date:
        where_parts.append("local_date <= ?")
        params.append(end_date)
    if where_parts:
        query += " WHERE " + " AND ".join(where_parts)
    query += " ORDER BY id"

    rows = conn.execute(query, params).fetchall()

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{table}.csv"
    with output_path.open("w", newline="", encoding="utf-8") as file_handle:
        writer = csv.writer(file_handle)
        writer.writerow(columns)
        writer.writerows(rows)
    print(f"Exported {table}: {len(rows)} rows -> {output_path}")


def parse_args() -> argparse.Namespace:
    # Load config/.env explicitly so HISTORY_DB_PATH resolves no matter where
    # this CLI is invoked from (the package keeps the env file under config/).
    env_path = Path(__file__).resolve().parent / "config" / ".env"
    load_dotenv(env_path, override=True)
    default_db = os.getenv("HISTORY_DB_PATH", "data/history.db")

    parser = argparse.ArgumentParser(description="Inspect and export history database")
    parser.add_argument("--db", default=default_db, help="Path to SQLite history DB")

    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("status", help="Show table row counts and observed ranges")

    export_parser = subparsers.add_parser("export", help="Export history tables to CSV")
    export_parser.add_argument(
        "--output-dir",
        default="history_exports",
        help="Directory to write CSV files",
    )
    export_parser.add_argument(
        "--start-date",
        help="Optional inclusive local-date filter (YYYY-MM-DD)",
    )
    export_parser.add_argument(
        "--end-date",
        help="Optional inclusive local-date filter (YYYY-MM-DD)",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    db_path = Path(args.db)
    if not db_path.exists():
        raise FileNotFoundError(f"History database not found: {db_path}")

    with connect(db_path) as conn:
        if args.command == "status":
            print_status(conn)
            return
        if args.command == "export":
            output_dir = Path(args.output_dir)
            for table in DEFAULT_TABLES:
                export_table(
                    conn,
                    table,
                    output_dir,
                    start_date=args.start_date,
                    end_date=args.end_date,
                )
            return

    raise ValueError(f"Unsupported command: {args.command}")


if __name__ == "__main__":
    main()
