"""Build clean-condition degradation trends, rates, and incident flags."""

import os
import sys

import duckdb

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "solar.duckdb")


def build_tables(con):
    print("Building degradation tables ...")
    con.execute("""
        CREATE OR REPLACE TABLE degradation_trend AS
        SELECT inverter_id, date_trunc('month', day)::DATE AS month,
               ROUND(SUM(actual_clean_kwh), 2) AS actual_kwh,
               ROUND(SUM(expected_clean_kwh), 2) AS expected_kwh,
               ROUND(SUM(actual_clean_kwh) / NULLIF(SUM(expected_clean_kwh), 0), 4) AS performance_ratio,
               ROUND(SUM(actual_clean_kwh - expected_clean_kwh), 2) AS delta_kwh,
               ROUND(SUM(clean_sun_kwh_m2), 2) AS sun_kwh_m2,
               ROUND(SUM(curtailment_hours), 2) AS curtailment_hours
        FROM expected_power
        WHERE NOT anomalous AND irradiation_coverage >= 0.95
        GROUP BY 1, 2
        ORDER BY 1, 2
    """)
    con.execute("""
        CREATE OR REPLACE TABLE degradation_rates AS
        WITH summer AS (
            SELECT inverter_id, month, performance_ratio,
                   date_diff('day', DATE '2017-07-01', month) / 365.25 AS years_since_baseline
            FROM degradation_trend
            WHERE month(month) BETWEEN 4 AND 9
              AND expected_kwh > 50
              AND performance_ratio BETWEEN 0 AND 1.3
        ), rates AS (
            SELECT inverter_id,
                   regr_slope(performance_ratio, years_since_baseline) * 100 AS degradation_rate_pct_yr,
                   COUNT(*) AS months_used,
                   corr(performance_ratio, years_since_baseline) AS trend_correlation
            FROM summer GROUP BY 1 HAVING COUNT(*) >= 12
        ), losses AS (
            SELECT inverter_id,
                   SUM(GREATEST(expected_clean_kwh - actual_clean_kwh, 0)) AS technical_lost_kwh
            FROM expected_power
            WHERE NOT anomalous AND irradiation_coverage >= 0.95 AND clean_sun_kwh_m2 >= 0.5
            GROUP BY 1
        )
        SELECT r.inverter_id,
               ROUND(r.degradation_rate_pct_yr, 3) AS degradation_rate_pct_yr,
               r.months_used, ROUND(r.trend_correlation, 3) AS trend_correlation,
               ROUND(l.technical_lost_kwh, 1) AS technical_lost_kwh
        FROM rates r JOIN losses l USING (inverter_id)
        ORDER BY degradation_rate_pct_yr
    """)
    con.execute("""
        CREATE OR REPLACE TABLE incident_flags AS
        SELECT inverter_id, day, actual_clean_kwh AS actual_kwh,
               expected_clean_kwh AS expected_kwh,
               ROUND(actual_clean_kwh / NULLIF(expected_clean_kwh, 0), 4) AS actual_ratio,
               ROUND(expected_clean_kwh - actual_clean_kwh, 2) AS lost_kwh,
               curtailed, curtailment_hours
        FROM expected_power
        WHERE NOT anomalous AND irradiation_coverage >= 0.95
          AND clean_sun_kwh_m2 >= 0.5 AND expected_clean_kwh > 1
          AND actual_clean_kwh / NULLIF(expected_clean_kwh, 0) < 0.70
        ORDER BY 1, 2
    """)
    con.execute("""
        CREATE OR REPLACE TABLE loss_attribution AS
        SELECT inverter_id, year(day) AS yr,
               ROUND(SUM(GREATEST(expected_clean_kwh - actual_clean_kwh, 0)), 1) AS technical_loss_kwh,
               ROUND(SUM(GREATEST(expected_curtailed_kwh - actual_curtailed_kwh, 0)), 1) AS curtailment_kwh,
               ROUND(SUM(GREATEST(expected_kwh - actual_kwh, 0)), 1) AS total_loss_kwh
        FROM expected_power
        WHERE NOT anomalous AND irradiation_coverage >= 0.95
        GROUP BY 1, 2 ORDER BY 1, 2
    """)


def report(con):
    print(con.execute("""
        SELECT inverter_id, degradation_rate_pct_yr, technical_lost_kwh
        FROM degradation_rates ORDER BY degradation_rate_pct_yr LIMIT 10
    """).df().to_string(index=False))
    print("Rows:", con.execute("""
        SELECT (SELECT COUNT(*) FROM degradation_trend),
               (SELECT COUNT(*) FROM degradation_rates),
               (SELECT COUNT(*) FROM incident_flags)
    """).fetchone())


def main():
    with duckdb.connect(DB_PATH) as con:
        build_tables(con)
        report(con)
    print("M3 done")


if __name__ == "__main__":
    main()
