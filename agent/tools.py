"""Read-only tools for the SolarMind decision agent."""

from db.db import run_query


def get_fleet_rank(inverter_id):
    """Return this inverter's rank, share, and fleet totals from v_fix_first."""
    safe_id = inverter_id.replace("'", "''")
    return run_query(f"""
        WITH ranked AS (
            SELECT inverter_id,
                   avoidable_loss_eur,
                   ROW_NUMBER() OVER (ORDER BY avoidable_loss_eur DESC) AS rank,
                   COUNT(*)         OVER ()                             AS total,
                   SUM(avoidable_loss_eur) OVER ()                     AS fleet_total_eur
            FROM v_fix_first
        )
        SELECT rank, total, avoidable_loss_eur, fleet_total_eur,
               ROUND(100.0 * avoidable_loss_eur / fleet_total_eur, 1) AS fleet_share_pct
        FROM ranked
        WHERE inverter_id = '{safe_id}'
    """)


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


def get_inverter_decision(inverter_id):
    """Return one inverter's validated ranking and uncertainty values."""
    safe_id = inverter_id.replace("'", "''")
    return run_query(f"""
        SELECT inverter_id, avoidable_loss_eur, avoidable_loss_kwh,
               curtailment_loss_eur, weather_uncertain_eur,
               degradation_rate_pct_yr, ci_low_pct_yr, ci_high_pct_yr,
               sample_months, low_confidence, confidence_reason,
               recommended_action
        FROM v_fix_first_with_uncertainty
        WHERE inverter_id = '{safe_id}'
    """)
