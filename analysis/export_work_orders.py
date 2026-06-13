"""Export validated Fix-First rankings as CSV and one-page PDF work orders."""

import os
import textwrap

import duckdb
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = os.path.dirname(os.path.dirname(__file__))
DB_PATH = os.path.join(ROOT, "solar.duckdb")
EXPORT_DIR = os.path.join(ROOT, "exports")
TOP_PDF_COUNT = 3


def build_table(con):
    con.execute("""
        CREATE OR REPLACE TABLE exportable_work_orders AS
        WITH recent_risk AS (
            SELECT inverter_id,
                   AVG(technical_loss_eur) FILTER (WHERE yr IN (2024, 2025)) AS annual_eur_at_risk,
                   AVG(technical_loss_kwh) FILTER (WHERE yr IN (2024, 2025)) AS annual_kwh_at_risk
            FROM revenue_loss
            GROUP BY 1
        ), tickets AS (
            SELECT component AS inverter_id, COUNT(*) AS ticket_count,
                   string_agg(DISTINCT category, '; ' ORDER BY category)
                     FILTER (WHERE category IS NOT NULL) AS ticket_categories
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
        ), joined AS (
            SELECT f.inverter_id,
                   f.avoidable_loss_eur AS lifetime_avoidable_loss_eur,
                   f.avoidable_loss_kwh AS lifetime_avoidable_loss_kwh,
                   ROUND(r.annual_eur_at_risk, 0) AS annual_eur_at_risk,
                   ROUND(r.annual_kwh_at_risk, 0) AS annual_kwh_at_risk,
                   f.curtailment_loss_eur,
                   f.degradation_rate_pct_yr,
                   f.recommended_action,
                   COALESCE(t.ticket_count, 0) AS ticket_count,
                   t.ticket_categories,
                   ft.fault_code, ft.fault_description,
                   ROUND(ft.fault_hours, 1) AS fault_hours,
                   dr.months_used, dr.trend_correlation
            FROM v_fix_first f
            JOIN recent_risk r USING (inverter_id)
            JOIN degradation_rates dr USING (inverter_id)
            LEFT JOIN tickets t USING (inverter_id)
            LEFT JOIN faults ft ON ft.inverter_id = f.inverter_id AND ft.fault_rank = 1
        )
        SELECT inverter_id, lifetime_avoidable_loss_eur, lifetime_avoidable_loss_kwh,
               annual_eur_at_risk, annual_kwh_at_risk, curtailment_loss_eur,
               degradation_rate_pct_yr,
               CASE
                 WHEN ticket_categories IS NOT NULL THEN ticket_categories
                 WHEN fault_description IS NOT NULL THEN fault_description
                 ELSE 'No specific historical cause in supplied evidence'
               END AS likely_cause_pattern,
               CASE
                 WHEN ticket_count > 0 AND fault_code IS NOT NULL
                      AND months_used >= 24 THEN 'high'
                 WHEN ticket_count > 0 OR fault_code IS NOT NULL THEN 'medium'
                 ELSE 'low'
               END AS confidence,
               ticket_count, ticket_categories, fault_code, fault_description,
               fault_hours, months_used, trend_correlation, recommended_action,
               'v_fix_first; revenue_loss; degradation_rates; fault_events; tickets_recent'
                 AS source_tables
        FROM joined
        ORDER BY lifetime_avoidable_loss_eur DESC
    """)


def render_pdf(row, path):
    fig = plt.figure(figsize=(8.27, 11.69))
    fig.patch.set_facecolor("white")
    fig.text(0.08, 0.94, "SolarMind Fix-First Work Order", fontsize=20, weight="bold")
    fig.text(0.08, 0.90, row.inverter_id, fontsize=16, color="#1f4e79", weight="bold")

    metrics = [
        ("Recent annual technical loss", f"EUR {row.annual_eur_at_risk:,.0f}/yr"),
        ("Lifetime avoidable loss (M4)", f"EUR {row.lifetime_avoidable_loss_eur:,.0f}"),
        ("Degradation trend", f"{row.degradation_rate_pct_yr:.3f}%/yr"),
        ("Curtailment loss (separate)", f"EUR {row.curtailment_loss_eur:,.0f}"),
        ("Evidence confidence", row.confidence.upper()),
    ]
    y = 0.84
    for label, value in metrics:
        fig.text(0.08, y, label, fontsize=10, color="#666666")
        fig.text(0.50, y, value, fontsize=12, weight="bold")
        y -= 0.045

    sections = [
        ("Likely cause pattern", row.likely_cause_pattern),
        ("Fault evidence", f"{row.fault_code}: {row.fault_description} ({row.fault_hours:.1f} h)"),
        ("Ticket evidence", row.ticket_categories or "No inverter-specific ticket in supplied data"),
        ("Recommended action", row.recommended_action),
        ("Traceability", row.source_tables),
    ]
    y -= 0.02
    for heading, content in sections:
        fig.text(0.08, y, heading, fontsize=12, weight="bold", color="#1f4e79")
        y -= 0.027
        wrapped = textwrap.fill(str(content), width=86)
        fig.text(0.08, y, wrapped, fontsize=10, va="top", linespacing=1.5)
        y -= 0.035 + 0.022 * wrapped.count("\n")

    fig.text(
        0.08, 0.07,
        "Historical evidence association only. Curtailment is excluded from Fix-First loss. "
        "All figures are generated from validated DuckDB tables.",
        fontsize=8.5, color="#666666", wrap=True,
    )
    fig.savefig(path, format="pdf", bbox_inches="tight")
    plt.close(fig)


def export_files(con):
    os.makedirs(EXPORT_DIR, exist_ok=True)
    frame = con.execute("SELECT * FROM exportable_work_orders").df()
    csv_path = os.path.join(EXPORT_DIR, "fix_first_work_orders.csv")
    frame.to_csv(csv_path, index=False)
    pdf_paths = []
    for row in frame.head(TOP_PDF_COUNT).itertuples(index=False):
        safe_id = row.inverter_id.replace(" ", "_").replace(".", "_")
        path = os.path.join(EXPORT_DIR, f"work_order_{safe_id}.pdf")
        render_pdf(row, path)
        pdf_paths.append(path)
    return frame, csv_path, pdf_paths


def validate(con, frame, csv_path, pdf_paths):
    m4_top = con.execute("""
        SELECT inverter_id, avoidable_loss_eur
        FROM v_fix_first ORDER BY avoidable_loss_eur DESC LIMIT 1
    """).fetchone()
    export_top = frame.iloc[0]
    if export_top.inverter_id != m4_top[0]:
        raise RuntimeError("Export top item does not match M4 ranking")
    if export_top.lifetime_avoidable_loss_eur != m4_top[1]:
        raise RuntimeError("Export top-item EUR does not match M4 exactly")
    if len(frame) != con.execute("SELECT COUNT(*) FROM v_fix_first").fetchone()[0]:
        raise RuntimeError("CSV does not contain one row per Fix-First inverter")
    if not os.path.exists(csv_path) or any(not os.path.exists(path) for path in pdf_paths):
        raise RuntimeError("One or more export files were not created")
    print(frame.head(TOP_PDF_COUNT).to_string(index=False))
    print(f"CSV: {csv_path}")
    print("PDFs:")
    for path in pdf_paths:
        print(f"  {path}")


def main():
    with duckdb.connect(DB_PATH) as con:
        build_table(con)
        frame, csv_path, pdf_paths = export_files(con)
        validate(con, frame, csv_path, pdf_paths)
    print("AI-91 done")


if __name__ == "__main__":
    main()
