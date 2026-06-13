"""Deterministic LangGraph decision agent over validated SolarMind tables."""

from typing import TypedDict
from urllib.parse import urlencode

from langgraph.graph import END, START, StateGraph

from agent.tools import get_fix_first, get_inverter_decision, get_work_order


class DecisionState(TypedDict, total=False):
    question: str
    limit: int
    page: str
    inverter_id: str
    ranking: list[dict]
    evidence: dict
    answer: str


def evidence_link(inverter_id, label, section="inverter-evidence"):
    """Link a table-backed answer value to its inverter evidence view."""
    query = urlencode({"page": "Inverter detail", "inverter": inverter_id})
    return f"[{label}](?{query}#{section})"


def query_validated_tables(state):
    inverter_id = state.get("inverter_id")
    if inverter_id:
        ranking = get_inverter_decision(inverter_id).to_dict("records")
    else:
        ranking = get_fix_first(state.get("limit", 5)).to_dict("records")
    evidence = {}
    if ranking:
        work_order = get_work_order(ranking[0]["inverter_id"])
        if not work_order.empty:
            evidence = work_order.iloc[0].to_dict()
    return {"ranking": ranking, "evidence": evidence}


def format_decision(state):
    rows = state.get("ranking", [])
    if not rows:
        return {"answer": "No validated Fix First rows are available."}

    inverter_id = state.get("inverter_id")
    if inverter_id:
        row = rows[0]
        confidence = "low confidence" if row["low_confidence"] else "supported trend"
        inverter = evidence_link(inverter_id, inverter_id)
        avoidable_eur = evidence_link(
            inverter_id, f"EUR {row['avoidable_loss_eur']:,.0f}", "annual-loss-attribution"
        )
        avoidable_kwh = evidence_link(
            inverter_id, f"{row['avoidable_loss_kwh']:,.0f} kWh", "annual-loss-attribution"
        )
        curtailment_eur = evidence_link(
            inverter_id, f"EUR {row['curtailment_loss_eur']:,.0f}", "annual-loss-attribution"
        )
        degradation = evidence_link(
            inverter_id, f"{row['degradation_rate_pct_yr']:.3f}%/yr",
            "output-versus-own-healthy-early-life-baseline",
        )
        ci = evidence_link(
            inverter_id,
            f"{row['ci_low_pct_yr']:.3f} to {row['ci_high_pct_yr']:.3f}",
            "output-versus-own-healthy-early-life-baseline",
        )
        sample_months = evidence_link(
            inverter_id, f"n={row['sample_months']} summer months",
            "output-versus-own-healthy-early-life-baseline",
        )
        lines = [
            f"Context: {state.get('page', 'Inverter detail')} / {inverter}",
            f"{inverter} has {avoidable_eur} validated avoidable loss "
            f"({avoidable_kwh}). Curtailment is separate at {curtailment_eur}.",
            f"Degradation: {degradation} (confidence interval {ci}, "
            f"{sample_months}; {confidence}).",
            f"Action: {row['recommended_action']}.",
        ]
        evidence = state.get("evidence", {})
        if evidence:
            opened_on = evidence_link(
                inverter_id, str(evidence.get("opened_on")), "service-tickets"
            )
            fault_code = evidence_link(
                inverter_id, str(evidence.get("primary_fault_code")), "fault-code-evidence"
            )
            lines.append(
                f"Evidence: ticket '{evidence.get('category')}' opened "
                f"{opened_on}; primary fault {fault_code} "
                f"({evidence.get('primary_fault_description')})."
            )
        lines.append(
            "Sources: v_fix_first_with_uncertainty and work_orders. "
            "Figures are reported without LLM recalculation."
        )
        return {"answer": "\n".join(lines)}

    lines = ["Fix First ranking (validated tables):"]
    for row in rows:
        inverter_id = row["inverter_id"]
        inverter = evidence_link(inverter_id, inverter_id)
        avoidable_eur = evidence_link(
            inverter_id, f"EUR {row['avoidable_loss_eur']:,.0f}", "annual-loss-attribution"
        )
        avoidable_kwh = evidence_link(
            inverter_id, f"{row['avoidable_loss_kwh']:,.0f} kWh", "annual-loss-attribution"
        )
        curtailment_eur = evidence_link(
            inverter_id, f"EUR {row['curtailment_loss_eur']:,.0f}", "annual-loss-attribution"
        )
        degradation = evidence_link(
            inverter_id, f"{row['degradation_rate_pct_yr']:.3f}%/yr",
            "output-versus-own-healthy-early-life-baseline",
        )
        lines.append(
            f"- {inverter}: {avoidable_eur} avoidable ({avoidable_kwh}), "
            f"{curtailment_eur} curtailment; trend {degradation}. "
            f"Action: {row['recommended_action']}."
        )

    evidence = state.get("evidence", {})
    if evidence:
        top_inverter = rows[0]["inverter_id"]
        opened_on = evidence_link(
            top_inverter, str(evidence.get("opened_on")), "service-tickets"
        )
        fault_code = evidence_link(
            top_inverter, str(evidence.get("primary_fault_code")), "fault-code-evidence"
        )
        lines.append(
            "Top-item evidence: "
            f"ticket '{evidence.get('category')}' opened {opened_on}; "
            f"primary fault {fault_code} "
            f"({evidence.get('primary_fault_description')})."
        )
    lines.append("Sources: v_fix_first and work_orders. Figures are reported without LLM recalculation.")
    return {"answer": "\n".join(lines)}


def build_agent():
    graph = StateGraph(DecisionState)
    graph.add_node("query_validated_tables", query_validated_tables)
    graph.add_node("format_decision", format_decision)
    graph.add_edge(START, "query_validated_tables")
    graph.add_edge("query_validated_tables", "format_decision")
    graph.add_edge("format_decision", END)
    return graph.compile()


AGENT = build_agent()


def ask(question, limit=5, page="Overview", inverter_id=None):
    """Answer the primary O&M prioritization question from live validated tables."""
    return AGENT.invoke({
        "question": question,
        "limit": limit,
        "page": page,
        "inverter_id": inverter_id,
    })["answer"]


if __name__ == "__main__":
    print(ask("What should I fix first, and why?"))
