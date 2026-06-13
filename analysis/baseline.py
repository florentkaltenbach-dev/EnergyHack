"""Build the healthy early-life baseline and daily expected-energy table."""

import os
import sys

import duckdb

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "solar.duckdb")
BASELINE_START = "2017-04-01"
BASELINE_END = "2017-10-01"
MIN_IRR = 50.0
FULL_SETPOINT = 99.5


def build_baseline(con):
    print(f"Building baseline from {BASELINE_START} to {BASELINE_END} ...")
    con.execute(f"""
        CREATE OR REPLACE TABLE baseline_pr AS
        WITH healthy AS (
            SELECT
                fp.inverter_id,
                SUM(fp.p_ac_kw) / 12.0 AS healthy_kwh,
                SUM(pl.irradiation_wm2) / 12.0 / 1000.0 AS healthy_sun_kwh_m2
            FROM fact_power fp
            JOIN fact_plant pl USING (ts)
            LEFT JOIN fault_events fe
              ON fe.inverter_id = fp.inverter_id AND fe.ts = fp.ts
            WHERE fp.ts >= '{BASELINE_START}' AND fp.ts < '{BASELINE_END}'
              AND pl.altitude_deg > 0
              AND pl.irradiation_wm2 > {MIN_IRR}
              AND (pl.dv_pct IS NULL OR pl.dv_pct >= {FULL_SETPOINT})
              AND (pl.evu_pct IS NULL OR pl.evu_pct >= {FULL_SETPOINT})
              AND fe.inverter_id IS NULL
            GROUP BY 1
        ), with_pr AS (
            SELECT h.inverter_id, di.kwp,
                   h.healthy_kwh,
                   h.healthy_sun_kwh_m2,
                   h.healthy_kwh / NULLIF(di.kwp * h.healthy_sun_kwh_m2, 0) AS baseline_pr
            FROM healthy h
            JOIN dim_inverters di USING (inverter_id)
        ), bounds AS (
            SELECT percentile_cont(0.25) WITHIN GROUP (ORDER BY baseline_pr) AS q1,
                   percentile_cont(0.75) WITHIN GROUP (ORDER BY baseline_pr) AS q3
            FROM with_pr
        )
        SELECT w.inverter_id, w.kwp,
               ROUND(w.healthy_kwh, 1) AS healthy_kwh,
               ROUND(w.healthy_sun_kwh_m2, 1) AS healthy_sun_kwh_m2,
               ROUND(w.baseline_pr, 4) AS baseline_pr,
               w.baseline_pr < b.q1 - 1.5 * (b.q3 - b.q1)
                 OR w.baseline_pr > b.q3 + 1.5 * (b.q3 - b.q1) AS anomalous
        FROM with_pr w CROSS JOIN bounds b
        ORDER BY 1
    """)
    print(con.execute("""
        SELECT COUNT(*) AS inverters, ROUND(AVG(baseline_pr), 3) AS avg_pr,
               ROUND(MIN(baseline_pr), 3) AS min_pr, ROUND(MAX(baseline_pr), 3) AS max_pr,
               SUM(anomalous::INTEGER) AS anomalous
        FROM baseline_pr
    """).df().to_string(index=False))


def build_expected_power(con):
    print("Building expected_power (daily, split by control state) ...")
    con.execute(f"""
        CREATE OR REPLACE TABLE expected_power AS
        WITH interval_data AS (
            SELECT fp.inverter_id, fp.ts::DATE AS day, fp.p_ac_kw,
                   pl.irradiation_wm2,
                   (COALESCE(pl.dv_pct, 100) < {FULL_SETPOINT}
                    OR COALESCE(pl.evu_pct, 100) < {FULL_SETPOINT}) AS curtailed,
                   pl.dv_pct, pl.evu_pct
            FROM fact_power fp
            JOIN fact_plant pl USING (ts)
            WHERE pl.altitude_deg > 0
        ), daily AS (
            SELECT inverter_id, day,
                   SUM(p_ac_kw) / 12.0 AS actual_kwh,
                   SUM(p_ac_kw) FILTER (WHERE NOT curtailed) / 12.0 AS actual_clean_kwh,
                   COALESCE(SUM(p_ac_kw) FILTER (WHERE curtailed), 0) / 12.0 AS actual_curtailed_kwh,
                   SUM(irradiation_wm2) / 12.0 / 1000.0 AS sun_kwh_m2,
                   SUM(irradiation_wm2) FILTER (WHERE NOT curtailed) / 12.0 / 1000.0 AS clean_sun_kwh_m2,
                   COALESCE(SUM(irradiation_wm2) FILTER (WHERE curtailed), 0) / 12.0 / 1000.0 AS curtailed_sun_kwh_m2,
                   COUNT(*) FILTER (WHERE curtailed) * 5.0 / 60.0 AS curtailment_hours,
                   MIN(dv_pct) FILTER (WHERE curtailed) AS min_dv_setpoint_pct,
                   MIN(evu_pct) FILTER (WHERE curtailed) AS min_evu_setpoint_pct,
                   COUNT(irradiation_wm2)::DOUBLE / NULLIF(COUNT(*), 0) AS irradiation_coverage
            FROM interval_data
            GROUP BY 1, 2
        )
        SELECT d.inverter_id, d.day,
               ROUND(d.actual_kwh, 3) AS actual_kwh,
               ROUND(d.actual_clean_kwh, 3) AS actual_clean_kwh,
               ROUND(d.actual_curtailed_kwh, 3) AS actual_curtailed_kwh,
               ROUND(b.baseline_pr * b.kwp * d.sun_kwh_m2, 3) AS expected_kwh,
               ROUND(b.baseline_pr * b.kwp * d.clean_sun_kwh_m2, 3) AS expected_clean_kwh,
               ROUND(b.baseline_pr * b.kwp * d.curtailed_sun_kwh_m2, 3) AS expected_curtailed_kwh,
               ROUND(d.actual_kwh - b.baseline_pr * b.kwp * d.sun_kwh_m2, 3) AS delta_kwh,
               ROUND(d.sun_kwh_m2, 3) AS sun_kwh_m2,
               ROUND(d.clean_sun_kwh_m2, 3) AS clean_sun_kwh_m2,
               ROUND(d.curtailed_sun_kwh_m2, 3) AS curtailed_sun_kwh_m2,
               d.curtailment_hours > 0 AS curtailed,
               ROUND(d.curtailment_hours, 3) AS curtailment_hours,
               d.min_dv_setpoint_pct, d.min_evu_setpoint_pct,
               ROUND(d.irradiation_coverage, 4) AS irradiation_coverage,
               b.baseline_pr, b.kwp, b.anomalous
        FROM daily d JOIN baseline_pr b USING (inverter_id)
        ORDER BY 1, 2
    """)
    print(f"expected_power: {con.execute('SELECT COUNT(*) FROM expected_power').fetchone()[0]:,} inverter-days")


def validate(con):
    result = con.execute("""
        SELECT ROUND(corr(actual_clean_kwh, expected_clean_kwh), 3) AS corr,
               ROUND(AVG((actual_clean_kwh - expected_clean_kwh) /
                     NULLIF(expected_clean_kwh, 0)) * 100, 2) AS bias_pct
        FROM expected_power
        WHERE day >= '2017-09-01' AND day < '2017-10-01'
          AND NOT anomalous AND clean_sun_kwh_m2 > 0.5
    """).df()
    print("Held-out September 2017:")
    print(result.to_string(index=False))


def main():
    with duckdb.connect(DB_PATH) as con:
        build_baseline(con)
        build_expected_power(con)
        validate(con)
    print("M2 done")


if __name__ == "__main__":
    main()
