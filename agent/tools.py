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
    - monitoring         → minute-level inverter power readings
    - error_events       → error codes with timestamps per inverter
    - error_descriptions → human-readable meaning of each error code
    - tariffs            → monthly electricity feed-in prices (€/kWh)
    - system_overview    → rated capacity (kWp) per inverter
    - tickets            → maintenance service records
    - tickets_detail     → extra detail rows for tickets (if present)

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
