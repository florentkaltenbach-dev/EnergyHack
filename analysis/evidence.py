"""Build evidence-backed work orders from validated analytical tables."""

import os

import duckdb

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "solar.duckdb")


def build_tables(con):
    con.execute("""
        CREATE OR REPLACE TABLE work_orders AS
        WITH tickets AS (
            SELECT component AS inverter_id,
                   TRY_CAST(startdate AS TIMESTAMPTZ)::DATE AS opened_on,
                   TRY_CAST(enddate AS TIMESTAMPTZ)::DATE AS closed_on,
                   category
            FROM tickets_recent
            WHERE component LIKE 'INV %'
              AND TRY_CAST(startdate AS TIMESTAMPTZ) IS NOT NULL
        ), ticket_loss AS (
            SELECT t.inverter_id, t.opened_on, t.closed_on, t.category,
                   SUM(f.technical_loss_kwh) AS loss_while_open_kwh,
                   SUM(f.technical_loss_eur) AS loss_while_open_eur
            FROM tickets t
            LEFT JOIN financial_loss f
              ON f.inverter_id = t.inverter_id
             AND f.day BETWEEN t.opened_on AND COALESCE(t.closed_on, CURRENT_DATE)
            GROUP BY 1, 2, 3, 4
        ), ranked_faults AS (
            SELECT t.inverter_id, t.opened_on,
                   COALESCE(d.hex, CAST(fe.error_code AS VARCHAR)) AS fault_code,
                   COALESCE(d.description, 'Unknown code') AS fault_description,
                   COUNT(*) * 5.0 / 60.0 AS fault_hours,
                   ROW_NUMBER() OVER (
                       PARTITION BY t.inverter_id, t.opened_on
                       ORDER BY COUNT(*) DESC
                   ) AS fault_rank
            FROM tickets t
            JOIN fault_events fe
              ON fe.inverter_id = t.inverter_id
             AND fe.ts::DATE BETWEEN t.opened_on - INTERVAL 90 DAY
                                  AND COALESCE(t.closed_on, t.opened_on) + INTERVAL 90 DAY
            LEFT JOIN dim_error_desc d USING (error_code)
            GROUP BY 1, 2, 3, 4
        )
        SELECT l.inverter_id, l.opened_on, l.closed_on, l.category,
               date_diff('day', l.opened_on, COALESCE(l.closed_on, CURRENT_DATE)) AS days_open,
               ROUND(COALESCE(l.loss_while_open_kwh, 0), 0) AS loss_while_open_kwh,
               ROUND(COALESCE(l.loss_while_open_eur, 0), 0) AS loss_while_open_eur,
               f.fault_code AS primary_fault_code,
               f.fault_description AS primary_fault_description,
               ROUND(COALESCE(f.fault_hours, 0), 1) AS primary_fault_hours,
               CASE
                 WHEN lower(COALESCE(l.category, '')) LIKE '%strang%'
                   THEN 'Inspect inverter and DC strings'
                 WHEN f.fault_code IS NOT NULL
                   THEN 'Inspect inverter and review recurring fault code'
                 ELSE 'Review service history and inverter performance'
               END AS recommended_action,
               'Historical association only; not a failure prediction.' AS evidence_scope
        FROM ticket_loss l
        LEFT JOIN ranked_faults f
          ON f.inverter_id = l.inverter_id
         AND f.opened_on = l.opened_on
         AND f.fault_rank = 1
        ORDER BY loss_while_open_eur DESC, opened_on
    """)


def validate(con):
    row = con.execute("""
        SELECT inverter_id, category, days_open, loss_while_open_eur,
               primary_fault_code, recommended_action
        FROM work_orders
        WHERE inverter_id = 'INV 01.07.045' AND category = 'Strangausfall'
    """).fetchone()
    if not row or row[3] <= 0 or not row[4]:
        raise RuntimeError("Demo work order is missing priced loss or fault evidence")
    print(row)


def main():
    with duckdb.connect(DB_PATH) as con:
        build_tables(con)
        validate(con)
    print("M5 done")


if __name__ == "__main__":
    main()
