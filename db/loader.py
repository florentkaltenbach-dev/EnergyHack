"""
P1 — Data Engineer
Load all raw Plant A files into solar.duckdb as a clean, queryable star schema.

Run once:   python db/loader.py
Re-runnable: it DROPs/CREATEs every table, so it's safe to run again.

Design notes (why this is not a trivial `SELECT * FROM parquet`):
  * timestamps arrive as TEXT "2016.12.31 22:00"  -> parsed to real TIMESTAMP
  * monitoring + errorcodes are WIDE (one col per inverter) -> melted to LONG
  * column names / German text contain encoding mojibake     -> cleaned
  * System_Overview uses "WR 01 .01 .001", monitoring uses "INV 01.01.001"
    -> normalised to a single inverter_id so tables join
"""

import os
import re
import sys
import duckdb
import pandas as pd

# Windows consoles default to cp1252, which can't encode ✅/box-drawing chars.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(ROOT, "solar.duckdb")
DATA = os.path.join(ROOT, "data")

TS_FMT = "%Y.%m.%d %H:%M"  # e.g. "2016.12.31 22:00"


# ── helpers ───────────────────────────────────────────────────────────────────
def norm_id(raw) -> str | None:
    """'WR 01 .01 .001' or 'INV 01.01.001 / P_AC (kW)' -> 'INV 01.01.001'."""
    m = re.findall(r"\d+", str(raw))
    if len(m) < 3:
        return None
    a, b, c = m[0], m[1], m[2]
    return f"INV {a.zfill(2)}.{b.zfill(2)}.{c.zfill(3)}"


def find_col(cols, *needles):
    """First column whose name contains ALL needles (case-insensitive)."""
    for c in cols:
        low = c.lower()
        if all(n.lower() in low for n in needles):
            return c
    return None


def q(name: str) -> str:
    """Quote an identifier for SQL, escaping embedded double-quotes."""
    return '"' + name.replace('"', '""') + '"'


def load_all_data():
    print(f"Database : {DB_PATH}")
    print(f"Data dir : {DATA}\n")
    con = duckdb.connect(DB_PATH)

    mon = os.path.join(DATA, "main_monitoring_data.parquet").replace("\\", "/")
    err = os.path.join(DATA, "errorcodes.parquet").replace("\\", "/")

    # ── stage raw monitoring with a real timestamp ────────────────────────────
    print("Staging monitoring parquet (parsing timestamps) ...")
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE _mon AS
        SELECT strptime("timestamp", '{TS_FMT}')::TIMESTAMP AS ts, *
        FROM read_parquet('{mon}')
    """)
    mon_cols = [d[0] for d in con.execute("DESCRIBE _mon").fetchall()]
    pac_cols = [c for c in mon_cols if "/ P_AC (kW)" in c and c.startswith("INV")]
    inv_ids = sorted({norm_id(c) for c in pac_cols})
    print(f"  inverters found: {len(inv_ids)}")

    # ── fact_power (LONG): one row per inverter per timestamp ──────────────────
    print("Building fact_power (long) ...")
    selects = []
    for inv in inv_ids:
        key = inv.split()[1]  # "01.01.001"
        pac = find_col(mon_cols, key, "P_AC")
        idc = find_col(mon_cols, key, "I_DC")
        udc = find_col(mon_cols, key, "U_DC")
        if not pac:
            continue
        selects.append(
            f"SELECT ts, '{inv}' AS inverter_id, "
            f"{q(pac)} AS p_ac_kw, "
            f"{(q(idc) + ' AS i_dc_a') if idc else 'NULL AS i_dc_a'}, "
            f"{(q(udc) + ' AS u_dc_v') if udc else 'NULL AS u_dc_v'} "
            f"FROM _mon"
        )
    con.execute("DROP TABLE IF EXISTS fact_power")
    con.execute("CREATE TABLE fact_power AS " + "\nUNION ALL\n".join(selects))
    n = con.execute("SELECT COUNT(*) FROM fact_power").fetchone()[0]
    print(f"  fact_power: {n:,} rows")

    # ── fact_plant (per timestamp): irradiation, weather, curtailment, grid ───
    print("Building fact_plant ...")
    plant_map = {
        "irradiation_wm2": find_col(mon_cols, "Irradiation"),
        "altitude_deg":    find_col(mon_cols, "Altitude"),
        "temp_ambient_c":  find_col(mon_cols, "Ambient"),
        "temp_module_c":   find_col(mon_cols, "Temperature", "Module"),
        "dv_pct":          find_col(mon_cols, "/ DV ("),
        "evu_pct":         find_col(mon_cols, "/ EVU ("),
        "plant_pac_kw":    find_col(mon_cols, "Janitza", "P_AC"),
        "cosphi":          find_col(mon_cols, "CosPhi"),
        "grid_i_ac_a":     find_col(mon_cols, "Janitza", "I_AC"),
        "grid_s_kva":      find_col(mon_cols, "S_AC"),
    }
    cols_sql = ["ts"]
    for alias, src in plant_map.items():
        cols_sql.append(f"{q(src)} AS {alias}" if src else f"NULL AS {alias}")
        print(f"    {alias:16s} <- {src}")
    con.execute("DROP TABLE IF EXISTS fact_plant")
    con.execute(f"CREATE TABLE fact_plant AS SELECT {', '.join(cols_sql)} FROM _mon")
    n = con.execute("SELECT COUNT(*) FROM fact_plant").fetchone()[0]
    print(f"  fact_plant: {n:,} rows")

    # ── fault_events (LONG, only real faults: error_code != 0) ────────────────
    print("Building fault_events (error_code != 0) ...")
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE _err AS
        SELECT strptime("timestamp", '{TS_FMT}')::TIMESTAMP AS ts, *
        FROM read_parquet('{err}')
    """)
    err_cols = [d[0] for d in con.execute("DESCRIBE _err").fetchall()]
    e_selects = []
    for inv in inv_ids:
        key = inv.split()[1]
        ec = find_col(err_cols, key, "Error")
        sc = find_col(err_cols, key, "Operational State")
        if not ec:
            continue
        e_selects.append(
            f"SELECT ts, '{inv}' AS inverter_id, "
            f"CAST({q(ec)} AS BIGINT) AS error_code, "
            f"{('CAST(' + q(sc) + ' AS BIGINT)') if sc else 'NULL'} AS op_state "
            f"FROM _err WHERE {q(ec)} IS NOT NULL AND {q(ec)} <> 0"
        )
    con.execute("DROP TABLE IF EXISTS fault_events")
    con.execute("CREATE TABLE fault_events AS " + "\nUNION ALL\n".join(e_selects))
    n = con.execute("SELECT COUNT(*) FROM fault_events").fetchone()[0]
    print(f"  fault_events: {n:,} rows")

    # ── dim_error_desc: code -> meaning ───────────────────────────────────────
    print("Building dim_error_desc ...")
    d = pd.read_excel(os.path.join(DATA, "Errorcodes", "errorcodes_description.xlsx"))
    d = d.rename(columns={
        d.columns[0]: "component",
        "Hex": "hex",
        "Dezimal": "error_code",
        "Code": "description",
    })
    con.register("_d", d)
    con.execute("DROP TABLE IF EXISTS dim_error_desc")
    con.execute("CREATE TABLE dim_error_desc AS SELECT * FROM _d")
    print(f"  dim_error_desc: {len(d):,} rows")

    # ── dim_inverters: capacity (kWp) etc. per inverter ───────────────────────
    print("Building dim_inverters ...")
    so = pd.read_excel(os.path.join(DATA, "Additional_Data", "System_Overview.xlsx"), header=2)
    so = so[so["WR-Type"] == "Inverter"].copy()
    so["inverter_id"] = so["Description"].map(norm_id)
    so = so.dropna(subset=["inverter_id"])
    for c in ["kWp Module", "Modules", "PDC (kWp)", "Strings"]:
        so[c] = pd.to_numeric(so.get(c), errors="coerce")
    # Some inverters have >1 module-type sub-array (e.g. INV 01.01.004): aggregate
    # capacity/module/string counts, keep the distinct module types joined.
    inv = so.groupby("inverter_id").agg(
        location=("Location", "first"),
        manufacturer=("Manufacturer", "first"),
        module_type=("Module Type", lambda s: " + ".join(sorted(set(s.dropna().astype(str))))),
        wp_per_module=("kWp Module", "max"),
        n_modules=("Modules", "sum"),
        kwp=("PDC (kWp)", "sum"),
        n_strings=("Strings", "sum"),
    ).reset_index()
    con.register("_inv", inv)
    con.execute("DROP TABLE IF EXISTS dim_inverters")
    con.execute("CREATE TABLE dim_inverters AS SELECT * FROM _inv")
    print(f"  dim_inverters: {len(inv):,} rows  (total {inv['kwp'].sum():.1f} kWp)")

    # ── dim_tariff: weekly feed-in price per inverter (eurocent/kWh) ───────────
    print("Building dim_tariff ...")
    try:
        raw = pd.read_excel(os.path.join(DATA, "Additional_Data", "feed-in-tarrifs.xlsx"),
                            sheet_name=0, header=None)
        # Layout: row 0 = junk headers, row 1 = weekly dates, rows 2+ = per-inverter tariffs.
        # Locate the date row robustly (first row that parses to mostly real dates).
        date_row = None
        for i in range(min(3, len(raw))):
            parsed = pd.to_datetime(raw.iloc[i, 1:], errors="coerce")
            if parsed.notna().mean() > 0.5:
                date_row = i
                break
        if date_row is None:
            raise ValueError("could not locate the weekly date header row")
        weeks = pd.to_datetime(raw.iloc[date_row, 1:], errors="coerce")
        rows = []
        for _, r in raw.iloc[date_row + 1:].iterrows():
            inv_id = norm_id(r.iloc[0])
            if not inv_id:
                continue
            for col_i, wk in zip(range(1, raw.shape[1]), weeks):
                val = pd.to_numeric(r.iloc[col_i], errors="coerce")
                if pd.notna(wk) and pd.notna(val):
                    rows.append((inv_id, wk.date(), float(val)))
        tdf = pd.DataFrame(rows, columns=["inverter_id", "week_start", "tariff_ct_kwh"])
        con.register("_t", tdf)
        con.execute("DROP TABLE IF EXISTS dim_tariff")
        con.execute("CREATE TABLE dim_tariff AS SELECT * FROM _t")
        print(f"  dim_tariff: {len(tdf):,} rows  ({tdf['week_start'].min()} -> {tdf['week_start'].max()})")
    except Exception as e:
        print(f"  WARN dim_tariff skipped: {e}")

    # ── tickets: two sheets, different schemas → two tables (names cleaned) ────
    print("Building tickets ...")
    xl = pd.ExcelFile(os.path.join(DATA, "Additional_Data", "Tickets.xlsx"))
    for sheet, tbl in [("2020-2026", "tickets_recent"), ("2019-2020", "tickets_legacy")]:
        if sheet not in xl.sheet_names:
            continue
        t = pd.read_excel(xl, sheet_name=sheet)
        t.columns = [re.sub(r"\W+", "_", str(c)).strip("_").lower() for c in t.columns]
        con.register("_tk", t)
        con.execute(f"DROP TABLE IF EXISTS {tbl}")
        con.execute(f"CREATE TABLE {tbl} AS SELECT * FROM _tk")
        print(f"  {tbl}: {len(t):,} rows")

    con.close()
    print("\n✅ Done — solar.duckdb is ready.")
    print('   Schema: python -c "from db.db import print_schema; print_schema()"')


if __name__ == "__main__":
    load_all_data()
