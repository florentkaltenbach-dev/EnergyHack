"""Read-only tools for the SolarMind decision agent."""

from db.db import run_query


def get_fix_first(limit=5):
    """Return the validated financial ranking without recalculating figures."""
    limit = max(1, min(int(limit), 20))
    return run_query(f"""
        SELECT inverter_id, avoidable_loss_eur, avoidable_loss_kwh,
               curtailment_loss_eur, weather_uncertain_eur,
               degradation_rate_pct_yr, recommended_action
        FROM v_fix_first
        ORDER BY avoidable_loss_eur DESC
        LIMIT {limit}
    """)


def get_work_order(inverter_id):
    """Return the strongest ticket/fault evidence for one inverter."""
    safe_id = inverter_id.replace("'", "''")
    return run_query(f"""
        SELECT * FROM work_orders
        WHERE inverter_id = '{safe_id}'
        ORDER BY loss_while_open_eur DESC, opened_on
        LIMIT 1
    """)
