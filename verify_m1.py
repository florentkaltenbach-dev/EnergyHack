"""M1 verification: join reconciliation, no orphan IDs, key SQL questions."""
import sys
sys.path.insert(0, ".")
from db.db import run_query

def check(label, sql, expect=None):
    df = run_query(sql)
    val = df.iloc[0, 0]
    ok = (val == expect) if expect is not None else (val == 0)
    status = "OK" if ok else "FAIL"
    print(f"  [{status}] {label}: {val}")
    return ok

print("=== M1: Join reconciliation ===")
all_ok = True

# Orphan inverter IDs
all_ok &= check("orphan fact_power inverters (not in dim_inverters)",
    "SELECT COUNT(DISTINCT fp.inverter_id) FROM fact_power fp "
    "LEFT JOIN dim_inverters di USING(inverter_id) WHERE di.inverter_id IS NULL")

all_ok &= check("orphan fault_events inverters",
    "SELECT COUNT(DISTINCT fe.inverter_id) FROM fault_events fe "
    "LEFT JOIN dim_inverters di USING(inverter_id) WHERE di.inverter_id IS NULL")

all_ok &= check("orphan dim_tariff inverters",
    "SELECT COUNT(DISTINCT dt.inverter_id) FROM dim_tariff dt "
    "LEFT JOIN dim_inverters di USING(inverter_id) WHERE di.inverter_id IS NULL")

all_ok &= check("orphan fact_power timestamps (not in fact_plant)",
    "SELECT COUNT(*) FROM (SELECT DISTINCT ts FROM fact_power) fp "
    "LEFT JOIN fact_plant pl USING(ts) WHERE pl.ts IS NULL")

print("\n=== M1: Key SQL questions ===")

# Production per inverter (top 5)
df = run_query("""
    SELECT inverter_id, ROUND(SUM(p_ac_kw)/12.0, 0) AS lifetime_kwh
    FROM fact_power GROUP BY 1 ORDER BY 2 DESC LIMIT 5
""")
print(f"\n  Top-5 inverters by lifetime kWh:\n{df.to_string(index=False)}")

# Curtailment hours
df = run_query("""
    SELECT
      ROUND(SUM(CASE WHEN dv_pct IS NOT NULL AND dv_pct < 99.5 THEN 5.0/60 ELSE 0 END), 0) AS dv_hours,
      ROUND(SUM(CASE WHEN evu_pct IS NOT NULL AND evu_pct < 99.5 THEN 5.0/60 ELSE 0 END), 0) AS evu_hours,
      ROUND(SUM(CASE WHEN (dv_pct IS NOT NULL AND dv_pct < 99.5)
                       OR (evu_pct IS NOT NULL AND evu_pct < 99.5)
                     THEN 5.0/60 ELSE 0 END), 0) AS any_curtail_hours
    FROM fact_plant
""")
print(f"\n  Curtailment hours:\n{df.to_string(index=False)}")

# Top error codes
df = run_query("""
    SELECT fe.error_code, de.description, ROUND(COUNT(*)*5/60.0, 0) AS hours
    FROM fault_events fe LEFT JOIN dim_error_desc de USING(error_code)
    GROUP BY 1,2 ORDER BY 3 DESC LIMIT 5
""")
print(f"\n  Top-5 fault codes by hours:\n{df.to_string(index=False)}")

# Revenue sample (one inverter, 2019)
df = run_query("""
    SELECT ROUND(SUM(fp.p_ac_kw/12.0 * dt.tariff_ct_kwh/100.0), 0) AS eur_2019
    FROM fact_power fp
    JOIN dim_tariff dt ON dt.inverter_id = fp.inverter_id
      AND dt.week_start = date_trunc('week', fp.ts)::DATE
    WHERE fp.inverter_id = 'INV 01.01.001'
      AND YEAR(fp.ts) = 2019
""")
print(f"\n  INV 01.01.001 revenue 2019: €{df.iloc[0,0]:,.0f}")

print(f"\n{'ALL OK' if all_ok else 'ISSUES FOUND'}")
