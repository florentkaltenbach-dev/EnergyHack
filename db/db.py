"""
P1 — Data Engineer
Shared database helper — P2 and P3 import from here.
Usage:
    from db.db import run_query, get_schema
"""

import os
import duckdb
import pandas as pd

# Resolve DB path relative to this file so imports work from any working dir
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "solar.duckdb")


def get_connection() -> duckdb.DuckDBPyConnection:
    """Return a read-only connection to the database."""
    if not os.path.exists(DB_PATH):
        raise FileNotFoundError(
            f"Database not found at {DB_PATH}\n"
            "Run:  python db/loader.py   to create it first."
        )
    return duckdb.connect(DB_PATH, read_only=True)


def run_query(sql: str) -> pd.DataFrame:
    """Execute SQL and return a pandas DataFrame."""
    con = get_connection()
    try:
        return con.execute(sql).df()
    finally:
        con.close()


def get_schema() -> str:
    """Return a human-readable schema of every table."""
    con = get_connection()
    try:
        tables = con.execute("SHOW TABLES").fetchall()
        if not tables:
            return "Database is empty — run db/loader.py first."
        parts = []
        for (name,) in tables:
            cols = con.execute(f"DESCRIBE {name}").fetchdf()
            col_lines = [
                f"  {row['column_name']}  {row['column_type']}"
                for _, row in cols.iterrows()
            ]
            # Row count
            count = con.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
            parts.append(
                f"TABLE {name}  ({count:,} rows)\n" + "\n".join(col_lines)
            )
        return "\n\n".join(parts)
    finally:
        con.close()


def print_schema():
    """Convenience: print schema to stdout."""
    print(get_schema())


if __name__ == "__main__":
    print_schema()
