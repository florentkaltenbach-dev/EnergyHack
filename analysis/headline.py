"""Fleet recoverable-€ headline — AI-84.

Aggregates technical (avoidable) loss from revenue_loss, annualises over the
covered period, and exposes the result as a fleet_headline VIEW.

Curtailment and weather-uncertain buckets are explicitly excluded — only
technical_loss_eur feeds the headline, reconciling directly to M4 line items.
"""

import os
import duckdb

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "solar.duckdb")


def build_tables(con):
    con.execute("""
        CREATE OR REPLACE VIEW fleet_headline AS
        WITH period AS (
            SELECT MIN(day) AS first_day,
                   MAX(day) AS last_day,
                   date_diff('day', MIN(day), MAX(day)) / 365.25 AS years_covered
            FROM financial_loss
        ), avoidable AS (
            SELECT inverter_id, SUM(technical_loss_eur) AS inverter_eur
            FROM revenue_loss
            GROUP BY 1
            HAVING SUM(technical_loss_eur) > 0
        ), ranked AS (
            SELECT inverter_id, inverter_eur,
                   ROW_NUMBER() OVER (ORDER BY inverter_eur DESC) AS rnk
            FROM avoidable
        ), totals AS (
            SELECT SUM(inverter_eur) AS total_eur, COUNT(*) AS n_inverters
            FROM avoidable
        ), top3 AS (
            SELECT SUM(inverter_eur) AS top3_eur FROM ranked WHERE rnk <= 3
        )
        SELECT ROUND(t.total_eur / p.years_covered, 0)  AS recoverable_eur_yr,
               ROUND(t.total_eur, 0)                    AS recoverable_eur_total,
               ROUND(p.years_covered, 1)                AS years_covered,
               p.first_day,
               p.last_day,
               t.n_inverters,
               ROUND(100.0 * top3.top3_eur / NULLIF(t.total_eur, 0), 1) AS top3_share_pct
        FROM totals t, period p, top3
    """)


def print_headline(con):
    row = con.execute("SELECT * FROM fleet_headline").fetchone()
    eur_yr, total_eur, years, first_day, last_day, n_inv, top3_pct = row
    print(f"Fleet recoverable: €{eur_yr:,.0f}/yr  ({first_day} – {last_day}, {years:.1f} yr)")
    print(f"  Period total: €{total_eur:,.0f}  |  {int(n_inv)} inverters  |  top-3 = {top3_pct:.1f}%")
    # Reconciliation check: fleet total must equal sum of per-inverter avoidable €
    per_inv_sum = con.execute(
        "SELECT ROUND(SUM(technical_loss_eur), 0) FROM revenue_loss"
    ).fetchone()[0]
    assert abs(total_eur - per_inv_sum) < 1, (
        f"Reconciliation failed: fleet €{total_eur} ≠ per-inverter sum €{per_inv_sum}"
    )
    print("  Reconciles to M4 line items OK")


def main():
    with duckdb.connect(DB_PATH) as con:
        build_tables(con)
        print_headline(con)
    print("AI-84 done")


if __name__ == "__main__":
    main()
