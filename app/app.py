"""SolarMind two-page Streamlit dashboard."""

import datetime
import os
import sys

import plotly.graph_objects as go
import streamlit as st
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from db.db import run_query
from analysis.leadtime import plot_timeline
from agent.agent import ask

DEMO_INV = "INV 01.07.045"  # Demo story: Strangausfall, 5yr open ticket, €5,309 technical loss

st.set_page_config(page_title="SolarMind", page_icon="☀️", layout="wide")


@st.cache_data(ttl=600)
def query(sql):
    return run_query(sql)


@st.cache_data(ttl=600)
def get_date_bounds():
    r = run_query(
        "SELECT MIN(day)::DATE AS min_d, MAX(day)::DATE AS max_d FROM financial_loss"
    ).iloc[0]
    return r.min_d, r.max_d


def fquery(sql, start, end):
    """Run a SQL query with $start/$end placeholders, result cached by the filled SQL."""
    filled = sql.replace("$start", f"'{start}'").replace("$end", f"'{end}'")
    return query(filled)


def seed_agent(prompt, context_key):
    st.session_state["agent_seed"] = prompt
    st.session_state["agent_seed_context"] = context_key


def update_page_route():
    page = st.session_state["selected_page"]
    st.query_params["page"] = page
    st.session_state["route_page"] = page
    if page == "Overview":
        st.query_params.pop("inverter", None)


def update_inverter_route():
    inverter_id = st.session_state["selected_inverter"]
    st.query_params["inverter"] = inverter_id
    st.session_state["route_inverter"] = inverter_id


# ---------------------------------------------------------------------------
# Agent section renderer
# ---------------------------------------------------------------------------

def render_agent_sections(sections):
    """Render a structured sections dict as sidebar expanders."""
    if not sections:
        return
    mode = sections.get("mode")
    if mode == "error":
        st.sidebar.warning(sections.get("message", "No data available."))
        return

    if sections.get("narrative"):
        st.sidebar.info(sections["narrative"])

    if mode == "inverter":
        rank = sections.get("rank")
        total = sections.get("total")
        share = sections.get("fleet_share_pct")
        fleet_total = sections.get("fleet_total_eur")
        if rank:
            st.sidebar.caption(
                f"Rank **#{rank}** of {total} · {share:.1f}% of fleet loss · "
                f"€{fleet_total:,.0f} fleet total"
            )

        fin = sections["financial"]
        with st.sidebar.expander("Financial loss", expanded=True):
            st.markdown(
                f"**Avoidable:** €{fin['avoidable_eur']:,.0f} · {fin['avoidable_kwh']:,.0f} kWh"
            )
            st.caption(f"Curtailment excluded: €{fin['curtailment_eur']:,.0f}")
            if fin["uncertain_eur"]:
                st.caption(f"Weather-uncertain: €{fin['uncertain_eur']:,.0f}")

        deg = sections["degradation"]
        ci_flag = "🔴 low confidence" if deg["low_confidence"] else "🟢 supported trend"
        with st.sidebar.expander(
            f"Degradation {deg['rate_pct_yr']:.2f}%/yr · {ci_flag}", expanded=False
        ):
            st.markdown(f"CI: {deg['ci_low']:.3f} to {deg['ci_high']:.3f} %/yr")
            st.caption(f"n={deg['months']} summer months · {deg['confidence']}")

        ev = sections.get("evidence", {})
        if ev and ev.get("category"):
            days = ev["days_open"]
            with st.sidebar.expander(
                f"Ticket: {ev['category']} · {days:.0f} days open", expanded=False
            ):
                st.caption(f"Opened: {ev['opened_on']}")
                if ev.get("closed_on") and ev["closed_on"] not in ("None", ""):
                    st.caption(f"Closed: {ev['closed_on']}")
                if ev.get("fault_code"):
                    st.markdown(f"**Fault {ev['fault_code']}:** {ev['fault_desc'][:100]}")

        st.sidebar.success(f"**Action:** {sections['recommendation']}")

    elif mode == "fleet":
        for row in sections.get("rows", []):
            with st.sidebar.expander(
                f"#{row['rank']} {row['inverter_id']} · €{row['avoidable_loss_eur']:,.0f}",
                expanded=(row["rank"] == 1),
            ):
                st.markdown(f"Degradation: **{row['degradation_rate_pct_yr']:.2f}%/yr**")
                st.caption(
                    f"{row['avoidable_loss_kwh']:,.0f} kWh lost · "
                    f"€{row['curtailment_loss_eur']:,.0f} curtailment"
                )
                st.caption(row["recommended_action"])

        ev = sections.get("evidence", {})
        if ev and ev.get("category"):
            st.sidebar.caption(
                f"Top-item evidence: {ev['category']} · fault {ev['fault_code']}"
            )


# ---------------------------------------------------------------------------
# Heatmap
# ---------------------------------------------------------------------------

def render_heatmap(start_date, end_date):
    losses = fquery("""
        SELECT inverter_id,
               ROUND(SUM(technical_loss_eur), 0) AS avoidable_eur
        FROM financial_loss
        WHERE day BETWEEN $start AND $end
        GROUP BY inverter_id
    """, start_date, end_date)

    if losses.empty:
        st.caption("No loss data for this period.")
        return

    losses["group"] = losses["inverter_id"].apply(lambda x: int(x.split(".")[1]))
    losses["unit"] = losses["inverter_id"].apply(lambda x: int(x.split(".")[2]))

    groups = sorted(losses["group"].unique())
    units = sorted(losses["unit"].unique())

    loss_map = {(int(r.group), int(r.unit)): r.avoidable_eur for _, r in losses.iterrows()}
    inv_map  = {(int(r.group), int(r.unit)): r.inverter_id  for _, r in losses.iterrows()}

    z, text = [], []
    for g in groups:
        row_z, row_text = [], []
        for u in units:
            val = loss_map.get((g, u))
            inv = inv_map.get((g, u), "")
            row_z.append(float(val) if val is not None else None)
            row_text.append(f"{inv}<br>€{val:,.0f}" if val is not None else "")
        z.append(row_z)
        text.append(row_text)

    fig = go.Figure(go.Heatmap(
        z=z,
        x=[f"{u:03d}" for u in units],
        y=[f"G{g:02d}" for g in groups],
        text=text,
        hovertemplate="%{text}<extra></extra>",
        colorscale=[[0, "#1a4731"], [0.35, "#f4a234"], [1, "#cc2222"]],
        colorbar=dict(title=dict(text="Avoidable €", font=dict(size=11))),
    ))
    fig.update_layout(
        height=300,
        margin=dict(l=50, r=10, t=10, b=30),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(title="Unit"),
        yaxis=dict(title="Group"),
    )
    st.plotly_chart(fig, use_container_width=True)


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

def overview(start_date, end_date):
    st.title("SolarMind: Fix First")
    st.caption("Losses are separated into unrestricted technical loss, plant curtailment, and weather-uncertain data.")

    totals = fquery("""
        SELECT ROUND(SUM(actual_kwh)/1000000, 2) AS production_gwh,
               ROUND(SUM(technical_loss_eur), 0)         AS avoidable_eur,
               ROUND(SUM(curtailment_loss_eur), 0)       AS curtailment_eur,
               ROUND(SUM(weather_uncertain_loss_eur), 0) AS uncertain_eur
        FROM financial_loss
        WHERE day BETWEEN $start AND $end
    """, start_date, end_date).iloc[0]

    fault_hours = fquery("""
        SELECT ROUND(COUNT(*) * 5 / 60.0, 0) AS hours
        FROM fault_events
        WHERE ts::DATE BETWEEN $start AND $end
    """, start_date, end_date).iloc[0, 0]

    cols = st.columns(5)
    cols[0].metric("Production", f"{totals.production_gwh:,.2f} GWh")
    cols[1].metric("Avoidable loss", f"€{totals.avoidable_eur:,.0f}")
    cols[2].metric("Curtailment", f"€{totals.curtailment_eur:,.0f}")
    cols[3].metric("Weather uncertain", f"€{totals.uncertain_eur:,.0f}")
    cols[4].metric("Fault hours", f"{fault_hours:,.0f}")

    # Heatmap
    st.subheader("Inverter loss heatmap")
    render_heatmap(start_date, end_date)

    title_col, action_col = st.columns([4, 1])
    title_col.subheader("Fix First ranking")
    action_col.button(
        "Explain this ranking",
        on_click=seed_agent,
        args=(
            "Explain why the top three inverters rank first and separate technical loss from curtailment.",
            "Overview:fleet",
        ),
        width="stretch",
    )
    ranking = fquery("""
        SELECT fl.inverter_id,
               ROUND(SUM(fl.technical_loss_eur), 0)         AS avoidable_loss_eur,
               ROUND(SUM(fl.technical_loss_kwh), 0)         AS avoidable_loss_kwh,
               ROUND(SUM(fl.curtailment_loss_eur), 0)       AS curtailment_loss_eur,
               ROUND(SUM(fl.weather_uncertain_loss_eur), 0) AS weather_uncertain_eur,
               dr.degradation_rate_pct_yr,
               CASE WHEN dr.degradation_rate_pct_yr <= -1 THEN 'Inspect inverter and DC strings'
                    ELSE 'Review recurring incidents' END   AS recommended_action
        FROM financial_loss fl
        LEFT JOIN degradation_rates dr USING (inverter_id)
        WHERE fl.day BETWEEN $start AND $end
        GROUP BY fl.inverter_id, dr.degradation_rate_pct_yr
        ORDER BY avoidable_loss_eur DESC
    """, start_date, end_date)

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

    # Lead-time section — historical analysis, intentionally not date-filtered
    try:
        lt = query("""
            SELECT COUNT(*)                         AS n_matched,
                   COUNT(days_to_ticket)            AS n_with_ticket,
                   ROUND(MEDIAN(days_to_ticket), 0) AS med_ticket,
                   ROUND(MEDIAN(days_to_error),  0) AS med_error
            FROM lead_time_matches
        """).iloc[0]
        st.subheader("Early-warning lead time")
        c1, c2, c3 = st.columns(3)
        c1.metric("Matched incidents", f"{int(lt.n_with_ticket)}")
        c2.metric("Median flag → ticket", f"{int(lt.med_ticket)} days")
        c3.metric("Median flag → error code", f"{int(lt.med_error)} days")

        example = query("""
            SELECT inverter_id,
                   incident_start::VARCHAR,
                   first_error_date::VARCHAR,
                   ticket_opened::VARCHAR,
                   days_to_error,
                   days_to_ticket
            FROM lead_time_matches
            WHERE days_to_ticket > 0
              AND days_to_error  > 0
              AND days_to_ticket > days_to_error
            ORDER BY days_to_ticket DESC
            LIMIT 1
        """)
        if example.empty:
            example = query("""
                SELECT inverter_id,
                       incident_start::VARCHAR,
                       first_error_date::VARCHAR,
                       ticket_opened::VARCHAR,
                       days_to_error,
                       days_to_ticket
                FROM lead_time_matches
                WHERE days_to_ticket > 0
                ORDER BY days_to_ticket DESC LIMIT 1
            """)
        if not example.empty:
            fig = plot_timeline(tuple(example.iloc[0]))
            st.pyplot(fig, clear_figure=True)
    except Exception:
        pass
    return None


def detail(start_date, end_date):
    st.title("Inverter evidence")
    inverter_ids = query("SELECT inverter_id FROM v_fix_first ORDER BY avoidable_loss_eur DESC")["inverter_id"].tolist()
    requested_inverter = st.query_params.get("inverter", DEMO_INV)
    default = inverter_ids.index(requested_inverter) if requested_inverter in inverter_ids else 0
    if st.session_state.get("route_inverter") != requested_inverter:
        st.session_state["selected_inverter"] = inverter_ids[default]
        st.session_state["route_inverter"] = inverter_ids[default]
    inv = st.sidebar.selectbox(
        "Inverter",
        inverter_ids,
        key="selected_inverter",
        on_change=update_inverter_route,
    )

    # Time-filtered KPIs for this inverter
    summary_df = fquery(f"""
        SELECT ROUND(SUM(fl.technical_loss_eur), 0)         AS avoidable_loss_eur,
               ROUND(SUM(fl.technical_loss_kwh), 0)         AS avoidable_loss_kwh,
               ROUND(SUM(fl.curtailment_loss_eur), 0)       AS curtailment_loss_eur,
               dr.degradation_rate_pct_yr,
               CASE WHEN dr.degradation_rate_pct_yr <= -1 THEN 'Inspect inverter and DC strings'
                    ELSE 'Review recurring incidents' END   AS recommended_action
        FROM financial_loss fl
        LEFT JOIN degradation_rates dr ON dr.inverter_id = fl.inverter_id
        WHERE fl.inverter_id = '{inv}'
          AND fl.day BETWEEN $start AND $end
        GROUP BY dr.degradation_rate_pct_yr
    """, start_date, end_date)

    if not summary_df.empty:
        summary = summary_df.iloc[0]
        deg_str = f"{summary.degradation_rate_pct_yr:,.2f}%/yr" if summary.degradation_rate_pct_yr is not None else "n/a"
        cols = st.columns(4)
        cols[0].metric("Avoidable loss", f"€{summary.avoidable_loss_eur:,.0f}")
        cols[1].metric("Lost energy", f"{summary.avoidable_loss_kwh:,.0f} kWh")
        cols[2].metric("Degradation trend", deg_str)
        cols[3].metric("Curtailment loss", f"€{summary.curtailment_loss_eur:,.0f}")
        st.info(summary.recommended_action)

    st.button(
        "Ask about this inverter",
        on_click=seed_agent,
        args=(
            f"Explain why {inv} needs attention, using its loss, degradation uncertainty, tickets, and faults.",
            f"Inverter detail:{inv}",
        ),
    )

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
        faults = fquery(f"""
            SELECT COALESCE(de.hex, CAST(fe.error_code AS VARCHAR)) AS code,
                   COALESCE(de.description, 'Unknown code')         AS description,
                   ROUND(COUNT(*) * 5 / 60.0, 1)                   AS hours
            FROM fault_events fe LEFT JOIN dim_error_desc de USING (error_code)
            WHERE fe.inverter_id = '{inv}'
              AND fe.ts::DATE BETWEEN $start AND $end
            GROUP BY 1, 2 ORDER BY hours DESC LIMIT 10
        """, start_date, end_date)
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

    losses = fquery(f"""
        SELECT year(day) AS yr,
               ROUND(SUM(technical_loss_eur), 2)         AS technical_loss_eur,
               ROUND(SUM(curtailment_loss_eur), 2)       AS curtailment_loss_eur,
               ROUND(SUM(weather_uncertain_loss_eur), 2) AS weather_uncertain_loss_eur
        FROM financial_loss
        WHERE inverter_id = '{inv}'
          AND day BETWEEN $start AND $end
        GROUP BY yr ORDER BY yr
    """, start_date, end_date)
    st.subheader("Annual loss attribution")
    if not losses.empty:
        st.bar_chart(
            losses.set_index("yr"),
            y=["technical_loss_eur", "curtailment_loss_eur", "weather_uncertain_loss_eur"],
        )
    return inv


# ---------------------------------------------------------------------------
# Agent rail
# ---------------------------------------------------------------------------

def agent_rail(page, inverter_id=None):
    st.sidebar.divider()
    enabled = st.sidebar.toggle("Decision agent", value=True, key="agent_enabled")
    if not enabled:
        return

    context = inverter_id if inverter_id else "fleet ranking"
    st.sidebar.caption(f"Context: {page} / {context}")
    context_key = f"{page}:{inverter_id or 'fleet'}"
    histories = st.session_state.setdefault("agent_histories", {})
    history = histories.setdefault(context_key, [])

    if st.session_state.get("agent_seed_context") == context_key:
        auto_question = st.session_state.pop("agent_seed")
        st.session_state.pop("agent_seed_context", None)
        with st.sidebar.spinner("Analysing…"):
            sections = ask(auto_question, page=page, inverter_id=inverter_id)
        history.append({"question": auto_question, "sections": sections})
        st.rerun()

    for item in history[-3:]:
        st.sidebar.markdown(f"**You:** {item['question']}")
        if "sections" in item:
            render_agent_sections(item["sections"])
        elif "answer" in item:
            st.sidebar.markdown(item["answer"])
        st.sidebar.divider()

    with st.sidebar.form("agent_rail_form", clear_on_submit=True):
        question = st.text_input("Ask why", placeholder="Why should I fix this first?")
        submitted = st.form_submit_button("Ask SolarMind", width="stretch")

    if submitted and question.strip():
        with st.sidebar.spinner("Analysing…"):
            sections = ask(question.strip(), page=page, inverter_id=inverter_id)
        history.append({"question": question.strip(), "sections": sections})
        st.rerun()


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Sidebar – time range selector
# ---------------------------------------------------------------------------
_PRESET_LABELS = ["7 days", "30 days", "90 days", "12 months", "All data", "Custom"]

if "period_key" not in st.session_state:
    st.session_state["period_key"] = "30 days"


def _pick_hotspot(hs, he):
    st.session_state["period_key"] = "Custom"
    st.session_state["date_range_slider"] = (hs, he)


try:
    min_d, max_d = get_date_bounds()

    if "date_range_slider" not in st.session_state:
        st.session_state["date_range_slider"] = (
            max(min_d, max_d - datetime.timedelta(days=30)), max_d
        )

    preset = st.sidebar.radio(
        "Period",
        _PRESET_LABELS,
        key="period_key",
        horizontal=True,
        label_visibility="collapsed",
    )

    if preset == "Custom":
        date_range = st.sidebar.slider(
            "Date range",
            min_value=min_d,
            max_value=max_d,
            format="YYYY-MM-DD",
            key="date_range_slider",
        )
        start_date, end_date = date_range
    else:
        _delta = {"7 days": 7, "30 days": 30, "90 days": 90, "12 months": 365}
        start_date = (
            min_d if preset == "All data"
            else max(min_d, max_d - datetime.timedelta(days=_delta[preset]))
        )
        end_date = max_d

    st.sidebar.caption(f"Showing: {start_date} – {end_date}")

    _hotspots = query("""
        SELECT DATE_TRUNC('month', day)::DATE AS period_start,
               ROUND(SUM(technical_loss_eur), 0) AS loss_eur,
               COUNT(DISTINCT CASE WHEN technical_loss_eur > 5 THEN inverter_id END) AS n_aff
        FROM financial_loss
        WHERE technical_loss_eur > 0
        GROUP BY 1
        ORDER BY loss_eur DESC
        LIMIT 5
    """)
    if not _hotspots.empty:
        st.sidebar.caption("High-loss months — click to jump:")
        for _, _r in _hotspots.iterrows():
            _ps = _r.period_start
            if hasattr(_ps, "date"):
                _ps = _ps.date()
            _pe = (
                datetime.date(_ps.year + 1, 1, 1) - datetime.timedelta(days=1)
                if _ps.month == 12
                else datetime.date(_ps.year, _ps.month + 1, 1) - datetime.timedelta(days=1)
            )
            _pe = min(_pe, max_d)
            _label = f"{_ps.strftime('%b %Y')} · €{int(_r.loss_eur):,} · {int(_r.n_aff)} inv"
            st.sidebar.button(
                _label,
                key=f"hs_{_ps}",
                on_click=_pick_hotspot,
                args=(_ps, _pe),
            )

except Exception:
    start_date = datetime.date(2017, 1, 1)
    end_date = datetime.date(2026, 12, 31)

st.sidebar.divider()

# --- Page navigation ---
pages = ["Overview", "Inverter detail"]
requested_page = st.query_params.get("page", "Overview")
page_index = pages.index(requested_page) if requested_page in pages else 0
if st.session_state.get("route_page") != requested_page:
    st.session_state["selected_page"] = pages[page_index]
    st.session_state["route_page"] = pages[page_index]
page = st.sidebar.radio(
    "Page",
    pages,
    key="selected_page",
    on_change=update_page_route,
)
selected_inverter = overview(start_date, end_date) if page == "Overview" else detail(start_date, end_date)
agent_rail(page, selected_inverter)
