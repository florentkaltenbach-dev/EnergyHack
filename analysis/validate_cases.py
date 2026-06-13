"""Reconcile the hero case and two additional inverters end to end."""

import os

import duckdb

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "solar.duckdb")
VALIDATED_INVERTERS = ("INV 01.07.045", "INV 01.07.047", "INV 01.08.057")
EXCLUDED_INVERTERS = ("INV 01.05.034",)


def sql_list(values):
    return ", ".join(f"'{value}'" for value in values)


def build_tables(con):
    selected = sql_list(VALIDATED_INVERTERS)
    excluded = sql_list(EXCLUDED_INVERTERS)
    common_ctes = """
        WITH summer AS (
            SELECT inverter_id,
                   AVG(performance_ratio) FILTER (
                       WHERE month >= DATE '2017-04-01' AND month < DATE '2017-10-01'
                   ) AS baseline_summer_pr,
                   AVG(performance_ratio) FILTER (
                       WHERE month >= DATE '2024-04-01'
                         AND month < DATE '2026-01-01'
                         AND month(month) BETWEEN 4 AND 9
                   ) AS recent_summer_pr
            FROM degradation_trend
            GROUP BY 1
        ), losses AS (
            SELECT inverter_id,
                   SUM(technical_loss_kwh) AS lifetime_technical_loss_kwh,
                   SUM(technical_loss_eur) AS lifetime_technical_loss_eur,
                   AVG(technical_loss_eur) FILTER (WHERE yr IN (2024, 2025)) AS recent_technical_eur_per_year,
                   SUM(curtailment_loss_eur) AS lifetime_curtailment_eur
            FROM revenue_loss
            GROUP BY 1
        ), tickets AS (
            SELECT component AS inverter_id, COUNT(*) AS ticket_count,
                   string_agg(DISTINCT category, '; ' ORDER BY category)
                     FILTER (WHERE category IS NOT NULL) AS ticket_evidence
            FROM tickets_recent
            WHERE component LIKE 'INV %'
            GROUP BY 1
        ), faults AS (
            SELECT fe.inverter_id,
                   COALESCE(d.hex, CAST(fe.error_code AS VARCHAR)) AS fault_code,
                   COALESCE(d.description, 'Unknown code') AS fault_description,
                   COUNT(*) * 5.0 / 60.0 AS fault_hours,
                   ROW_NUMBER() OVER (
                       PARTITION BY fe.inverter_id ORDER BY COUNT(*) DESC
                   ) AS fault_rank
            FROM fault_events fe
            LEFT JOIN dim_error_desc d USING (error_code)
            GROUP BY 1, 2, 3
        ), cases AS (
            SELECT d.inverter_id, d.degradation_rate_pct_yr,
                   s.baseline_summer_pr, s.recent_summer_pr,
                   l.lifetime_technical_loss_kwh, l.lifetime_technical_loss_eur,
                   l.recent_technical_eur_per_year, l.lifetime_curtailment_eur,
                   COALESCE(t.ticket_count, 0) AS ticket_count, t.ticket_evidence,
                   f.fault_code, f.fault_description, f.fault_hours,
                   100 * l.lifetime_curtailment_eur /
                     NULLIF(l.lifetime_technical_loss_eur + l.lifetime_curtailment_eur, 0)
                     AS curtailment_share_pct
            FROM degradation_rates d
            JOIN summer s USING (inverter_id)
            JOIN losses l USING (inverter_id)
            LEFT JOIN tickets t USING (inverter_id)
            LEFT JOIN faults f ON f.inverter_id = d.inverter_id AND f.fault_rank = 1
        )
    """
    con.execute(f"""
        CREATE OR REPLACE TABLE validation_cases AS
        {common_ctes}
        SELECT inverter_id,
               ROUND(degradation_rate_pct_yr, 3) AS degradation_pct_per_year,
               ROUND(baseline_summer_pr * 100, 1) AS baseline_summer_pr_pct,
               ROUND(recent_summer_pr * 100, 1) AS recent_summer_pr_pct,
               ROUND((recent_summer_pr - baseline_summer_pr) * 100, 1) AS summer_gap_pp,
               ROUND(recent_technical_eur_per_year, 0) AS recent_technical_eur_per_year,
               ROUND(lifetime_technical_loss_eur, 0) AS lifetime_technical_loss_eur,
               ROUND(lifetime_technical_loss_kwh, 0) AS lifetime_technical_loss_kwh,
               ROUND(curtailment_share_pct, 1) AS curtailment_share_pct,
               curtailment_share_pct < 10 AS curtailment_clear,
               ticket_count, ticket_evidence,
               fault_code AS primary_fault_code,
               fault_description AS primary_fault_description,
               ROUND(fault_hours, 1) AS primary_fault_hours
        FROM cases
        WHERE inverter_id IN ({selected})
        ORDER BY CASE inverter_id
                   WHEN 'INV 01.07.045' THEN 1
                   WHEN 'INV 01.07.047' THEN 2
                   WHEN 'INV 01.08.057' THEN 3
                 END
    """)
    con.execute(f"""
        CREATE OR REPLACE TABLE validation_exclusions AS
        {common_ctes}
        SELECT inverter_id,
               ROUND(degradation_rate_pct_yr, 3) AS degradation_pct_per_year,
               ROUND(curtailment_share_pct, 1) AS curtailment_share_pct,
               ROUND(recent_technical_eur_per_year, 0) AS recent_technical_eur_per_year,
               CASE
                 WHEN curtailment_share_pct >= 10
                   THEN 'Excluded: curtailment is too large a share of priced loss'
                 WHEN degradation_rate_pct_yr > -1
                   THEN 'Excluded: weak long-term degradation signal'
                 ELSE 'Excluded after evidence review'
               END AS exclusion_reason
        FROM cases
        WHERE inverter_id IN ({excluded})
        ORDER BY inverter_id
    """)


def validate(con):
    cases = con.execute("SELECT * FROM validation_cases").df()
    exclusions = con.execute("SELECT * FROM validation_exclusions").df()
    if len(cases) != 3 or cases["inverter_id"].nunique() != 3:
        raise RuntimeError("Expected exactly three reconciled validation cases")
    if not cases["curtailment_clear"].all():
        raise RuntimeError("A selected validation case is not curtailment-clear")
    if (cases["recent_technical_eur_per_year"] <= 0).any():
        raise RuntimeError("A selected validation case has no traceable recent annual loss")
    if cases["primary_fault_code"].isna().any():
        raise RuntimeError("A selected validation case has no fault evidence")
    if exclusions.empty:
        raise RuntimeError("At least one rejected candidate must be recorded")
    print("Validated cases:")
    print(cases.to_string(index=False))
    print("\nRecorded exclusions:")
    print(exclusions.to_string(index=False))


def main():
    with duckdb.connect(DB_PATH) as con:
        build_tables(con)
        validate(con)
    print("AI-86 done")


if __name__ == "__main__":
    main()
