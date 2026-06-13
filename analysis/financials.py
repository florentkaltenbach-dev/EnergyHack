"""Price validated technical, curtailment, and uncertain energy losses."""

import os
import sys

import duckdb

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "solar.duckdb")


def build_tables(con):
    print("Building financial_loss ...")
    con.execute("""
        CREATE OR REPLACE TABLE financial_loss AS
        WITH priced AS (
            SELECT ep.*,
                   dt.tariff_ct_kwh,
                   ep.irradiation_coverage >= 0.95 AND ep.sun_kwh_m2 >= 0.5 AS reliable_weather
            FROM expected_power ep
            LEFT JOIN dim_tariff dt
              ON dt.inverter_id = ep.inverter_id
             AND dt.week_start = date_trunc('week', ep.day)::DATE
            WHERE NOT ep.anomalous
        ), bucketed AS (
            SELECT *,
                   CASE WHEN reliable_weather
                        THEN GREATEST(expected_clean_kwh - actual_clean_kwh, 0) ELSE 0 END AS technical_loss_kwh,
                   CASE WHEN reliable_weather
                        THEN GREATEST(expected_curtailed_kwh - actual_curtailed_kwh, 0) ELSE 0 END AS curtailment_loss_kwh,
                   CASE WHEN NOT reliable_weather
                        THEN GREATEST(expected_kwh - actual_kwh, 0) ELSE 0 END AS weather_uncertain_loss_kwh
            FROM priced
        )
        SELECT inverter_id, day, actual_kwh, expected_kwh,
               ROUND(technical_loss_kwh + curtailment_loss_kwh + weather_uncertain_loss_kwh, 3) AS lost_kwh,
               ROUND(technical_loss_kwh, 3) AS technical_loss_kwh,
               ROUND(curtailment_loss_kwh, 3) AS curtailment_loss_kwh,
               ROUND(weather_uncertain_loss_kwh, 3) AS weather_uncertain_loss_kwh,
               curtailed AS curtailed_flag, curtailment_hours,
               min_dv_setpoint_pct, min_evu_setpoint_pct,
               reliable_weather, tariff_ct_kwh,
               ROUND(technical_loss_kwh * tariff_ct_kwh / 100, 4) AS technical_loss_eur,
               ROUND(curtailment_loss_kwh * tariff_ct_kwh / 100, 4) AS curtailment_loss_eur,
               ROUND(weather_uncertain_loss_kwh * tariff_ct_kwh / 100, 4) AS weather_uncertain_loss_eur
        FROM bucketed
        ORDER BY 1, 2
    """)
    con.execute("""
        CREATE OR REPLACE TABLE revenue_loss AS
        SELECT inverter_id, year(day) AS yr,
               ROUND(SUM(actual_kwh), 1) AS actual_kwh,
               ROUND(SUM(expected_kwh), 1) AS expected_kwh,
               ROUND(SUM(actual_kwh * tariff_ct_kwh / 100), 2) AS actual_eur,
               ROUND(SUM(expected_kwh * tariff_ct_kwh / 100), 2) AS expected_eur,
               ROUND(SUM(technical_loss_kwh), 1) AS technical_loss_kwh,
               ROUND(SUM(curtailment_loss_kwh), 1) AS curtailment_loss_kwh,
               ROUND(SUM(weather_uncertain_loss_kwh), 1) AS weather_uncertain_loss_kwh,
               ROUND(SUM(technical_loss_eur), 2) AS technical_loss_eur,
               ROUND(SUM(curtailment_loss_eur), 2) AS curtailment_loss_eur,
               ROUND(SUM(weather_uncertain_loss_eur), 2) AS weather_uncertain_loss_eur
        FROM financial_loss
        GROUP BY 1, 2 ORDER BY 1, 2
    """)
    con.execute("""
        CREATE OR REPLACE VIEW v_fix_first AS
        SELECT r.inverter_id,
               ROUND(SUM(r.technical_loss_eur), 0) AS avoidable_loss_eur,
               ROUND(SUM(r.technical_loss_kwh), 0) AS avoidable_loss_kwh,
               ROUND(SUM(r.curtailment_loss_eur), 0) AS curtailment_loss_eur,
               ROUND(SUM(r.weather_uncertain_loss_eur), 0) AS weather_uncertain_eur,
               dr.degradation_rate_pct_yr,
               CASE WHEN dr.degradation_rate_pct_yr <= -1 THEN 'Inspect inverter and DC strings'
                    ELSE 'Review recurring incidents' END AS recommended_action
        FROM revenue_loss r
        LEFT JOIN degradation_rates dr USING (inverter_id)
        GROUP BY r.inverter_id, dr.degradation_rate_pct_yr
        ORDER BY avoidable_loss_eur DESC
    """)


def validate(con):
    missing_tariff = con.execute("SELECT COUNT(*) FROM financial_loss WHERE tariff_ct_kwh IS NULL").fetchone()[0]
    if missing_tariff:
        raise RuntimeError(f"{missing_tariff} financial rows have no tariff")
    totals = con.execute("""
        SELECT ROUND(SUM(technical_loss_eur), 0) AS technical_eur,
               ROUND(SUM(curtailment_loss_eur), 0) AS curtailment_eur,
               ROUND(SUM(weather_uncertain_loss_eur), 0) AS uncertain_eur,
               ROUND(SUM(expected_eur), 0) AS potential_eur,
               ROUND(100 * SUM(technical_loss_eur) / NULLIF(SUM(expected_eur), 0), 2) AS technical_pct
        FROM revenue_loss
    """).df()
    print(totals.to_string(index=False))
    print("Fix First:")
    print(con.execute("SELECT * FROM v_fix_first LIMIT 10").df().to_string(index=False))


def main():
    with duckdb.connect(DB_PATH) as con:
        build_tables(con)
        validate(con)
    print("M4 done")


if __name__ == "__main__":
    main()
