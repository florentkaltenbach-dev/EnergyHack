"""Verify evidence work orders and exact decision-agent financial values."""

from agent.agent import ask
from agent.tools import get_fix_first
from db.db import run_query


work_order = run_query("""
    SELECT * FROM work_orders
    WHERE inverter_id = 'INV 01.07.045' AND category = 'Strangausfall'
""")
assert not work_order.empty
assert work_order.iloc[0].loss_while_open_eur > 0
assert work_order.iloc[0].primary_fault_code

top = get_fix_first(3)
answer = ask("What should I fix first, and why?", limit=3)
for row in top.itertuples():
    assert row.inverter_id in answer
    assert f"EUR {row.avoidable_loss_eur:,.0f}" in answer

print(answer)

context_answer = ask(
    "Why this inverter?",
    page="Inverter detail",
    inverter_id="INV 01.07.045",
)
assert "Context: Inverter detail / INV 01.07.045" in context_answer
assert "EUR 5,309" in context_answer
assert "95% CI" in context_answer
print("\nContext-aware answer:\n" + context_answer)
print("M5/M6 verification passed")
