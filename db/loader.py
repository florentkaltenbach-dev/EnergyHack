"""
P1 — Data Engineer
Run this ONCE to load all raw data files into solar.duckdb
Usage: python db/loader.py
"""

import duckdb
import pandas as pd
import os
import sys

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "solar.duckdb")
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")


def load_all_data():
    print(f"Creating database at: {DB_PATH}")
    print(f"Reading data from:    {DATA_DIR}\n")

    con = duckdb.connect(DB_PATH)

    # ── 1. Main monitoring data (minute-resolution readings) ──────────────────
    path = os.path.join(DATA_DIR, "main_monitoring_data.parquet")
    if os.path.exists(path):
        con.execute(f"""
            CREATE OR REPLACE TABLE monitoring AS
            SELECT * FROM read_parquet('{path}')
        """)
        count = con.execute("SELECT COUNT(*) FROM monitoring").fetchone()[0]
        print(f"✓ monitoring          {count:,} rows")
    else:
        print(f"⚠ MISSING: {path}")

    # ── 2. Error events ────────────────────────────────────────────────────────
    path = os.path.join(DATA_DIR, "errorcodes.parquet")
    if os.path.exists(path):
        con.execute(f"""
            CREATE OR REPLACE TABLE error_events AS
            SELECT * FROM read_parquet('{path}')
        """)
        count = con.execute("SELECT COUNT(*) FROM error_events").fetchone()[0]
        print(f"✓ error_events        {count:,} rows")
    else:
        print(f"⚠ MISSING: {path}")

    # ── 3. Feed-in tariffs ────────────────────────────────────────────────────
    path = os.path.join(DATA_DIR, "Additional_Data", "feed-in-tarrifs.xlsx")
    if os.path.exists(path):
        df = pd.read_excel(path)
        con.register("_tariffs", df)
        con.execute("CREATE OR REPLACE TABLE tariffs AS SELECT * FROM _tariffs")
        print(f"✓ tariffs             {len(df):,} rows")
    else:
        print(f"⚠ MISSING: {path}")

    # ── 4. System overview (inverter capacities) ──────────────────────────────
    path = os.path.join(DATA_DIR, "Additional_Data", "System_Overview.xlsx")
    if os.path.exists(path):
        df = pd.read_excel(path)
        con.register("_system", df)
        con.execute("CREATE OR REPLACE TABLE system_overview AS SELECT * FROM _system")
        print(f"✓ system_overview     {len(df):,} rows")
    else:
        print(f"⚠ MISSING: {path}")

    # ── 5. Service tickets (two sheets) ───────────────────────────────────────
    path = os.path.join(DATA_DIR, "Additional_Data", "Tickets.xlsx")
    if os.path.exists(path):
        xl = pd.ExcelFile(path)
        df1 = pd.read_excel(xl, sheet_name=0)
        con.register("_tickets", df1)
        con.execute("CREATE OR REPLACE TABLE tickets AS SELECT * FROM _tickets")
        print(f"✓ tickets             {len(df1):,} rows  (sheet 1: {xl.sheet_names[0]})")
        if len(xl.sheet_names) > 1:
            df2 = pd.read_excel(xl, sheet_name=1)
            con.register("_tickets2", df2)
            con.execute("CREATE OR REPLACE TABLE tickets_detail AS SELECT * FROM _tickets2")
            print(f"✓ tickets_detail      {len(df2):,} rows  (sheet 2: {xl.sheet_names[1]})")
    else:
        print(f"⚠ MISSING: {path}")

    # ── 6. Error code descriptions ────────────────────────────────────────────
    path = os.path.join(DATA_DIR, "Errorcodes", "errorcodes_description.xlsx")
    if os.path.exists(path):
        df = pd.read_excel(path)
        con.register("_errdescs", df)
        con.execute("CREATE OR REPLACE TABLE error_descriptions AS SELECT * FROM _errdescs")
        print(f"✓ error_descriptions  {len(df):,} rows")
    else:
        print(f"⚠ MISSING: {path}")

    con.close()
    print(f"\n✅ Done — solar.duckdb is ready.")
    print(f"   Next: run  python -c \"from db.db import print_schema; print_schema()\"")


if __name__ == "__main__":
    load_all_data()
