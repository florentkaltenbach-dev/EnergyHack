"""LangGraph decision agent over validated SolarMind tables.

Three nodes: query → format (structured sections) → LLM narrative.
Returns a sections dict instead of a flat string so the UI can
render each evidence layer in its own expander.
"""

from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from agent.tools import (
    get_fix_first,
    get_fleet_rank,
    get_inverter_decision,
    get_work_order,
)


class DecisionState(TypedDict, total=False):
    question: str
    limit: int
    page: str
    inverter_id: str
    ranking: list[dict]
    evidence: dict
    fleet_rank: dict
    sections: dict


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_recommendation(row, evidence):
    """Derive a specific action from fault/ticket evidence."""
    days_open = float(evidence.get("days_open") or 0)
    category = str(evidence.get("category") or "")
    fault_desc = str(evidence.get("primary_fault_description") or "")
    cat_l = category.lower()
    fault_l = fault_desc.lower()

    if "strang" in cat_l:
        return f"Replace DC strings — '{category}' open {days_open:.0f} days confirms permanent loss"
    if "string" in fault_l:
        return f"Inspect DC strings — string fault recurs ({fault_desc[:55]})"
    if any(t in fault_l for t in ("temperatur", "überhitz", "kühler")):
        return f"Check thermal management — {fault_desc[:65]}"
    if "netz" in fault_l:
        return f"Investigate grid connection — {fault_desc[:65]}"
    if days_open > 730:
        return f"Escalate — '{category}' unresolved {days_open:.0f} days, ongoing revenue loss"
    if days_open > 180:
        return f"Re-open ticket — '{category}' open {days_open:.0f} days, still losing revenue"
    if row.get("low_confidence"):
        return "Schedule on-site inspection — degradation signal uncertain, verify hardware"
    return row.get("recommended_action", "Inspect inverter and DC strings")


# ---------------------------------------------------------------------------
# Node 1: query DB
# ---------------------------------------------------------------------------

def query_validated_tables(state):
    inverter_id = state.get("inverter_id")
    if inverter_id:
        ranking = get_inverter_decision(inverter_id).to_dict("records")
        fleet_df = get_fleet_rank(inverter_id)
        fleet_rank = fleet_df.iloc[0].to_dict() if not fleet_df.empty else {}
    else:
        ranking = get_fix_first(state.get("limit", 5)).to_dict("records")
        fleet_rank = {}

    evidence = {}
    if ranking:
        wo = get_work_order(ranking[0]["inverter_id"])
        if not wo.empty:
            evidence = wo.iloc[0].to_dict()

    return {"ranking": ranking, "evidence": evidence, "fleet_rank": fleet_rank}


# ---------------------------------------------------------------------------
# Node 2: structure into sections dict
# ---------------------------------------------------------------------------

def format_decision(state):
    rows = state.get("ranking", [])
    if not rows:
        return {"sections": {"mode": "error", "message": "No validated Fix First rows available."}}

    inverter_id = state.get("inverter_id")
    evidence = state.get("evidence", {})

    if inverter_id:
        row = rows[0]
        fleet = state.get("fleet_rank", {})

        ev_dict = {
            "category": str(evidence.get("category") or ""),
            "days_open": float(evidence.get("days_open") or 0),
            "opened_on": str(evidence.get("opened_on") or ""),
            "closed_on": str(evidence.get("closed_on") or ""),
            "fault_code": str(evidence.get("primary_fault_code") or ""),
            "fault_desc": str(evidence.get("primary_fault_description") or ""),
        } if evidence else {}

        sections = {
            "mode": "inverter",
            "inverter_id": inverter_id,
            "rank": int(fleet["rank"]) if fleet.get("rank") else None,
            "total": int(fleet["total"]) if fleet.get("total") else None,
            "fleet_share_pct": float(fleet["fleet_share_pct"]) if fleet.get("fleet_share_pct") else None,
            "fleet_total_eur": float(fleet["fleet_total_eur"]) if fleet.get("fleet_total_eur") else None,
            "financial": {
                "avoidable_eur": float(row["avoidable_loss_eur"]),
                "avoidable_kwh": float(row["avoidable_loss_kwh"]),
                "curtailment_eur": float(row["curtailment_loss_eur"]),
                "uncertain_eur": float(row.get("weather_uncertain_eur") or 0),
            },
            "degradation": {
                "rate_pct_yr": float(row["degradation_rate_pct_yr"]),
                "ci_low": float(row["ci_low_pct_yr"]),
                "ci_high": float(row["ci_high_pct_yr"]),
                "months": int(row["sample_months"]),
                "low_confidence": bool(row["low_confidence"]),
                "confidence": "low confidence" if row["low_confidence"] else "supported trend",
            },
            "evidence": ev_dict,
            "recommendation": _build_recommendation(row, evidence),
            "narrative": "",
        }
        return {"sections": sections}

    # Fleet ranking mode
    ranked_rows = [
        {
            "rank": i,
            "inverter_id": r["inverter_id"],
            "avoidable_loss_eur": float(r["avoidable_loss_eur"]),
            "avoidable_loss_kwh": float(r["avoidable_loss_kwh"]),
            "curtailment_loss_eur": float(r["curtailment_loss_eur"]),
            "degradation_rate_pct_yr": float(r["degradation_rate_pct_yr"]),
            "recommended_action": r["recommended_action"],
        }
        for i, r in enumerate(rows, 1)
    ]

    ev_dict = {
        "category": str(evidence.get("category") or ""),
        "days_open": float(evidence.get("days_open") or 0),
        "fault_code": str(evidence.get("primary_fault_code") or ""),
        "fault_desc": str(evidence.get("primary_fault_description") or ""),
    } if evidence else {}

    sections = {
        "mode": "fleet",
        "rows": ranked_rows,
        "evidence": ev_dict,
        "narrative": "",
    }
    return {"sections": sections}


# ---------------------------------------------------------------------------
# Node 3: LLM narrative
# ---------------------------------------------------------------------------

def generate_narrative(state):
    sections = state.get("sections", {})
    if not sections or sections.get("mode") == "error":
        return {}

    question = state.get("question", "")

    try:
        from dotenv import load_dotenv
        load_dotenv()
        from langchain_groq import ChatGroq

        llm = ChatGroq(model="llama-3.3-70b-versatile", temperature=0.7, max_tokens=200)

        if sections["mode"] == "inverter":
            inv = sections["inverter_id"]
            rank = sections.get("rank")
            total = sections.get("total")
            fin = sections["financial"]
            deg = sections["degradation"]
            ev = sections.get("evidence", {})

            context_lines = [
                f"Solar inverter {inv}, ranked #{rank} of {total}.",
                f"Avoidable loss: €{fin['avoidable_eur']:,.0f} ({fin['avoidable_kwh']:,.0f} kWh).",
                f"Degradation: {deg['rate_pct_yr']:.3f}%/yr "
                f"(CI {deg['ci_low']:.3f} to {deg['ci_high']:.3f}, "
                f"n={deg['months']} months, {deg['confidence']}).",
            ]
            if ev and ev.get("category"):
                context_lines.append(f"Ticket: '{ev['category']}' open {ev['days_open']:.0f} days.")
                context_lines.append(f"Primary fault: {ev['fault_code']} — {ev['fault_desc'][:80]}.")
            context = "\n".join(context_lines)
            prompt = (
                f"{context}\n\n"
                f"User question: {question}\n\n"
                "Answer in 2–3 sentences using the data above. Be specific about root cause and "
                "financial impact. No generic advice."
            )

        else:
            rows = sections.get("rows", [])
            fleet_total = sum(r["avoidable_loss_eur"] for r in rows)
            top3 = rows[:3]
            top3_share = 100 * sum(r["avoidable_loss_eur"] for r in top3) / fleet_total if fleet_total else 0
            summary = ", ".join(
                f"{r['inverter_id']} €{r['avoidable_loss_eur']:,.0f} ({r['degradation_rate_pct_yr']:.1f}%/yr)"
                for r in top3
            )
            context = (
                f"Solar fleet Fix First ranking. Fleet total: €{fleet_total:,.0f} avoidable loss.\n"
                f"Top 3: {summary}. Top-3 share: {top3_share:.1f}%."
            )
            prompt = (
                f"{context}\n\n"
                f"User question: {question}\n\n"
                "Answer in 2–3 sentences using the data above. Be specific. No generic advice."
            )

        narrative = llm.invoke(prompt).content.strip()
    except Exception:
        narrative = ""

    return {"sections": {**sections, "narrative": narrative}}


# ---------------------------------------------------------------------------
# Graph
# ---------------------------------------------------------------------------

def build_agent():
    graph = StateGraph(DecisionState)
    graph.add_node("query_validated_tables", query_validated_tables)
    graph.add_node("format_decision", format_decision)
    graph.add_node("generate_narrative", generate_narrative)
    graph.add_edge(START, "query_validated_tables")
    graph.add_edge("query_validated_tables", "format_decision")
    graph.add_edge("format_decision", "generate_narrative")
    graph.add_edge("generate_narrative", END)
    return graph.compile()


AGENT = build_agent()


def ask(question, limit=5, page="Overview", inverter_id=None):
    """Return a structured sections dict for the UI to render."""
    result = AGENT.invoke({
        "question": question,
        "limit": limit,
        "page": page,
        "inverter_id": inverter_id,
    })
    return result.get("sections", {})


if __name__ == "__main__":
    import json
    print(json.dumps(ask("What should I fix first, and why?"), indent=2, default=str))
