"""Deterministic LangGraph decision agent over validated SolarMind tables."""

from typing import TypedDict

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
        lines = [
            f"Context: {state.get('page', 'Inverter detail')} / {inverter_id}",
            f"{inverter_id} has EUR {row['avoidable_loss_eur']:,.0f} validated avoidable loss "
            f"({row['avoidable_loss_kwh']:,.0f} kWh). Curtailment is separate at "
            f"EUR {row['curtailment_loss_eur']:,.0f}.",
            f"Degradation: {row['degradation_rate_pct_yr']:.3f}%/yr "
            f"(95% CI {row['ci_low_pct_yr']:.3f} to {row['ci_high_pct_yr']:.3f}, "
            f"n={row['sample_months']} summer months; {confidence}).",
            f"Action: {row['recommended_action']}.",
        ]
        evidence = state.get("evidence", {})
        if evidence:
            lines.append(
                f"Evidence: ticket '{evidence.get('category')}' opened "
                f"{evidence.get('opened_on')}; primary fault "
                f"{evidence.get('primary_fault_code')} "
                f"({evidence.get('primary_fault_description')})."
            )
        lines.append(
            "Sources: v_fix_first_with_uncertainty and work_orders. "
            "Figures are reported without LLM recalculation."
        )
        return {"answer": "\n".join(lines)}

    lines = ["Fix First ranking (validated tables):"]
    for index, row in enumerate(rows, 1):
        lines.append(
            f"{index}. {row['inverter_id']}: EUR {row['avoidable_loss_eur']:,.0f} "
            f"avoidable ({row['avoidable_loss_kwh']:,.0f} kWh), "
            f"EUR {row['curtailment_loss_eur']:,.0f} curtailment; "
            f"trend {row['degradation_rate_pct_yr']:.3f}%/yr. "
            f"Action: {row['recommended_action']}."
        )

    evidence = state.get("evidence", {})
    if evidence:
        lines.append(
            "Top-item evidence: "
            f"ticket '{evidence.get('category')}' opened {evidence.get('opened_on')}; "
            f"primary fault {evidence.get('primary_fault_code')} "
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
