"""
P2 — Agent Engineer
LangChain tools that the AI agent can call.
"""

import pandas as pd
import plotly.express as px
import plotly.io as pio
from langchain_core.tools import tool

from db.db import run_query, get_schema

# ── Chart state (simple module-level store for hackathon) ─────────────────────
# invoke_agent() resets this before each run, then reads it after.
_last_chart = None


# ── Tool 1: Get schema ────────────────────────────────────────────────────────
@tool
def get_database_schema() -> str:
    """
    Get the schema of every table in the solar plant database,
    including column names and types.
    Always call this first so you know the exact column names before writing SQL.
    """
    try:
        return get_schema()
    except Exception as e:
        return f"Error getting schema: {e}"


# ── Tool 2: Run SQL ───────────────────────────────────────────────────────────
@tool
def query_database(sql: str) -> str:
    """
    Execute a SQL query against the solar plant DuckDB database.
    Returns results as a JSON string (max 200 rows).

    Database tables:
    - fact_power     → power per inverter, LONG (ts, inverter_id, p_ac_kw, i_dc_a, u_dc_v)
    - fact_plant     → plant-wide per timestamp (ts, irradiation_wm2, altitude_deg,
                       dv_pct, evu_pct, plant_pac_kw, temp_module_c, ...)
    - fault_events   → real faults only (ts, inverter_id, error_code, op_state)
    - dim_error_desc → error_code/hex → description (error_code DECIMAL, hex e.g. '0A0013')
    - dim_inverters  → nameplate per inverter (inverter_id, kwp, module_type, ...)
    - dim_tariff     → weekly feed-in price (inverter_id, week_start, tariff_ct_kwh ct/kWh)
    - tickets_recent / tickets_legacy → maintenance records

    Analytics VIEWS (use for Performance-Ratio / ranking / trend questions):
    - v_inverter_month_pr (inverter_id, month, kwh, kwp, sun_kwh_m2, pr)
    - v_inverter_day_pr   (inverter_id, day,   kwh, kwp, sun_kwh_m2, pr)
    - v_inverter_summary  (inverter_id, kwp, lifetime_kwh, specific_yield_kwh_per_kwp,
                           avg_pr, fault_hours)

    Units: energy kWh = SUM(p_ac_kw)/12.0 (5-min data); revenue € = kWh*tariff_ct_kwh/100.
    PR = (kWh/kWp)/(SUM(irradiation_wm2)/12/1000). inverter_id looks like 'INV 01.01.001'.
    Never compare raw kWh across inverters (different sizes) — use pr / specific_yield.

    DuckDB supports standard SQL plus:
    - date_trunc('month', col)
    - strftime(col, '%Y-%m')
    - epoch_ms() for timestamps

    Always check column names via get_database_schema() before writing queries.
    """
    try:
        df = run_query(sql)
        if df.empty:
            return "Query returned no rows."
        total = len(df)
        if total > 200:
            df = df.head(200)
            suffix = f"\n[Showing first 200 of {total:,} rows]"
        else:
            suffix = ""
        return df.to_json(orient="records", date_format="iso") + suffix
    except Exception as e:
        return f"SQL Error: {e}\n\nHint: run get_database_schema() to check column names."


# ── Tool 3: Create chart ──────────────────────────────────────────────────────
@tool
def create_chart(
    data_json: str,
    chart_type: str,
    x_col: str,
    y_col: str,
    title: str,
    color_col: str = "",
) -> str:
    """
    Create a Plotly chart from query results and display it in the UI.

    Args:
        data_json:  JSON string from query_database
        chart_type: "bar" | "line" | "scatter" | "pie"
        x_col:      column name for the X axis (or 'names' for pie)
        y_col:      column name for the Y axis (or 'values' for pie)
        title:      chart title
        color_col:  optional column to use for colour grouping (pass "" to skip)

    Returns a confirmation string; the chart is stored and rendered by the UI.
    """
    global _last_chart
    try:
        # Strip the row-count suffix if present
        json_part = data_json.split("\n[Showing")[0].strip()
        df = pd.read_json(json_part, orient="records")

        color = color_col if color_col else None

        if chart_type == "bar":
            fig = px.bar(df, x=x_col, y=y_col, title=title, color=color)
        elif chart_type == "line":
            fig = px.line(df, x=x_col, y=y_col, title=title, color=color,
                          markers=True)
        elif chart_type == "scatter":
            fig = px.scatter(df, x=x_col, y=y_col, title=title, color=color)
        elif chart_type == "pie":
            fig = px.pie(df, names=x_col, values=y_col, title=title)
        else:
            return f"Unknown chart_type '{chart_type}'. Use bar, line, scatter, or pie."

        fig.update_layout(template="plotly_white")
        _last_chart = fig
        return f"Chart created: '{title}'"
    except Exception as e:
        return f"Chart error: {e}"
