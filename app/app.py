"""SolarMind two-page Streamlit dashboard."""

import os
import sys

import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from db.db import run_query

DEMO_INV = "INV 01.07.045"  # Demo story: Strangausfall, 5yr open ticket, €5,309 technical loss

st.set_page_config(page_title="SolarMind", page_icon="☀️", layout="wide")


@st.cache_data(ttl=600)
def query(sql):
    return run_query(sql)


def overview():
    st.title("SolarMind: Fix First")
    st.caption("Losses are separated into unrestricted technical loss, plant curtailment, and weather-uncertain data.")

    totals = query("""
        SELECT ROUND(SUM(actual_kwh)/1000000, 2) AS production_gwh,
               ROUND(SUM(technical_loss_eur), 0) AS avoidable_eur,
               ROUND(SUM(curtailment_loss_eur), 0) AS curtailment_eur,
               ROUND(SUM(weather_uncertain_loss_eur), 0) AS uncertain_eur
        FROM revenue_loss
    """).iloc[0]
    fault_hours = query("SELECT ROUND(COUNT(*) * 5 / 60.0, 0) AS hours FROM fault_events").iloc[0, 0]
    cols = st.columns(5)
    cols[0].metric("Production", f"{totals.production_gwh:,.2f} GWh")
    cols[1].metric("Avoidable loss", f"€{totals.avoidable_eur:,.0f}")
    cols[2].metric("Curtailment", f"€{totals.curtailment_eur:,.0f}")
    cols[3].metric("Weather uncertain", f"€{totals.uncertain_eur:,.0f}")
    cols[4].metric("Fault hours", f"{fault_hours:,.0f}")

    st.subheader("Fix First ranking")
    ranking = query("SELECT * FROM v_fix_first ORDER BY avoidable_loss_eur DESC")
    st.dataframe(
        ranking.rename(columns={
            "inverter_id": "Inverter", "avoidable_loss_eur": "Avoidable €",
            "avoidable_loss_kwh": "Avoidable kWh", "curtailment_loss_eur": "Curtailment €",
            "weather_uncertain_eur": "Uncertain €", "degradation_rate_pct_yr": "Trend %/yr",
            "recommended_action": "Action",
        }),
        hide_index=True, width="stretch",
        column_config={"Avoidable €": st.column_config.NumberColumn(format="€ %.0f")},
    )


def detail():
    st.title("Inverter evidence")
    inverter_ids = query("SELECT inverter_id FROM v_fix_first ORDER BY avoidable_loss_eur DESC")["inverter_id"].tolist()
    default = inverter_ids.index(DEMO_INV) if DEMO_INV in inverter_ids else 0
    inv = st.sidebar.selectbox("Inverter", inverter_ids, index=default)

    summary = query(f"SELECT * FROM v_fix_first WHERE inverter_id = '{inv}'").iloc[0]
    cols = st.columns(4)
    cols[0].metric("Avoidable loss", f"€{summary.avoidable_loss_eur:,.0f}")
    cols[1].metric("Lost energy", f"{summary.avoidable_loss_kwh:,.0f} kWh")
    cols[2].metric("Degradation trend", f"{summary.degradation_rate_pct_yr:,.2f}%/yr")
    cols[3].metric("Curtailment loss", f"€{summary.curtailment_loss_eur:,.0f}")
    st.info(summary.recommended_action)

    if inv == DEMO_INV:
        st.warning(
            "**Demo story:** This inverter passed every PR check in summer 2020 (93–105 %). "
            "But vs its own year-1 baseline (100.4 %) it had already lost €124 that year. "
            "A *Strangausfall* (string failure) ticket was open for **1,736 days** (Oct 2020 – Jul 2025). "
            "Total technical loss: **€5,309** — 94 % on uncurtailed days. "
            "SolarMind would have flagged the −6.8 pp deviation in **July 2020**, "
            "3 months before the ticket and 9 months before a standard 80 % threshold would alarm."
        )

    trend = query(f"""
        SELECT month, performance_ratio * 100 AS pct_of_early_life
        FROM degradation_trend WHERE inverter_id = '{inv}' ORDER BY month
    """)
    st.subheader("Output versus own healthy early-life baseline")
    st.line_chart(trend.set_index("month"), y="pct_of_early_life", y_label="% of baseline")

    left, right = st.columns(2)
    with left:
        st.subheader("Fault-code evidence")
        faults = query(f"""
            SELECT COALESCE(de.hex, CAST(fe.error_code AS VARCHAR)) AS code,
                   COALESCE(de.description, 'Unknown code') AS description,
                   ROUND(COUNT(*) * 5 / 60.0, 1) AS hours
            FROM fault_events fe LEFT JOIN dim_error_desc de USING (error_code)
            WHERE fe.inverter_id = '{inv}'
            GROUP BY 1, 2 ORDER BY hours DESC LIMIT 10
        """)
        st.dataframe(faults, hide_index=True, width="stretch")
    with right:
        st.subheader("Service tickets")
        tickets = query(f"""
            SELECT startdate, enddate, category
            FROM tickets_recent WHERE component = '{inv}' ORDER BY startdate
        """)
        if tickets.empty:
            st.caption("No inverter-specific ticket in the supplied recent-ticket table.")
        else:
            st.dataframe(tickets, hide_index=True, width="stretch")

    work_order = query(f"""
        SELECT opened_on, closed_on, category, days_open, loss_while_open_eur,
               primary_fault_code, primary_fault_description, recommended_action,
               evidence_scope
        FROM work_orders WHERE inverter_id = '{inv}'
        ORDER BY loss_while_open_eur DESC LIMIT 1
    """)
    if not work_order.empty:
        st.subheader("Evidence-backed work order")
        st.dataframe(work_order, hide_index=True, width="stretch")

    losses = query(f"""
        SELECT yr, technical_loss_eur, curtailment_loss_eur, weather_uncertain_loss_eur
        FROM revenue_loss WHERE inverter_id = '{inv}' ORDER BY yr
    """)
    st.subheader("Annual loss attribution")
    st.bar_chart(losses.set_index("yr"), y=["technical_loss_eur", "curtailment_loss_eur", "weather_uncertain_loss_eur"])


page = st.sidebar.radio("Page", ["Overview", "Inverter detail"])
overview() if page == "Overview" else detail()
