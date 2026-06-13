"""Measure normalized inverter performance before and after closed tickets."""

import os

import duckdb
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "solar.duckdb")
WINDOW_DAYS = 90
MIN_VALID_DAYS = 20


def build_table(con):
    con.execute(f"""
        CREATE OR REPLACE TABLE repair_effectiveness AS
        WITH tickets AS (
            SELECT component AS inverter_id,
                   TRY_CAST(startdate AS TIMESTAMPTZ)::DATE AS opened_on,
                   TRY_CAST(enddate AS TIMESTAMPTZ)::DATE AS closed_on,
                   category
            FROM tickets_recent
            WHERE component LIKE 'INV %'
              AND TRY_CAST(startdate AS TIMESTAMPTZ) IS NOT NULL
              AND TRY_CAST(enddate AS TIMESTAMPTZ) IS NOT NULL
        ), measured AS (
            SELECT t.inverter_id, t.opened_on, t.closed_on, t.category,
                   AVG(ep.actual_clean_kwh / NULLIF(ep.expected_clean_kwh, 0)) FILTER (
                       WHERE ep.day >= t.opened_on - INTERVAL {WINDOW_DAYS} DAY
                         AND ep.day < t.opened_on
                   ) AS before_ratio,
                   COUNT(ep.actual_clean_kwh / NULLIF(ep.expected_clean_kwh, 0)) FILTER (
                       WHERE ep.day >= t.opened_on - INTERVAL {WINDOW_DAYS} DAY
                         AND ep.day < t.opened_on
                   ) AS before_days,
                   AVG(ep.actual_clean_kwh / NULLIF(ep.expected_clean_kwh, 0)) FILTER (
                       WHERE ep.day > t.closed_on
                         AND ep.day <= t.closed_on + INTERVAL {WINDOW_DAYS} DAY
                   ) AS after_ratio,
                   COUNT(ep.actual_clean_kwh / NULLIF(ep.expected_clean_kwh, 0)) FILTER (
                       WHERE ep.day > t.closed_on
                         AND ep.day <= t.closed_on + INTERVAL {WINDOW_DAYS} DAY
                   ) AS after_days
            FROM tickets t
            JOIN expected_power ep USING (inverter_id)
            WHERE ep.irradiation_coverage >= 0.95
              AND ep.clean_sun_kwh_m2 >= 0.5
              AND NOT ep.anomalous
            GROUP BY 1, 2, 3, 4
        ), scored AS (
            SELECT *, (after_ratio - before_ratio) * 100 AS delta_pp
            FROM measured
            WHERE before_days >= {MIN_VALID_DAYS}
              AND after_days >= {MIN_VALID_DAYS}
              AND before_ratio IS NOT NULL
              AND after_ratio IS NOT NULL
        )
        SELECT inverter_id, opened_on, closed_on, category,
               {WINDOW_DAYS} AS window_days,
               before_days, after_days,
               ROUND(before_ratio * 100, 1) AS before_performance_pct,
               ROUND(after_ratio * 100, 1) AS after_performance_pct,
               ROUND(delta_pp, 1) AS delta_pp,
               CASE
                 WHEN ROUND(delta_pp, 1) >= 15 THEN 'recovered'
                 WHEN ROUND(delta_pp, 1) >= 5 THEN 'partial'
                 WHEN ROUND(delta_pp, 1) > -5 THEN 'no-change'
                 ELSE 'worse'
               END AS outcome,
               CASE
                 WHEN ROUND(delta_pp, 1) >= 15 THEN 'Post-close performance improved by at least 15 pp'
                 WHEN ROUND(delta_pp, 1) >= 5 THEN 'Post-close performance improved by 5-15 pp'
                 WHEN ROUND(delta_pp, 1) > -5 THEN 'Change remained within +/-5 pp'
                 ELSE 'Post-close performance declined by at least 5 pp'
               END AS classification_rule
        FROM scored
        ORDER BY delta_pp DESC, inverter_id, closed_on
    """)


def pick_example(con):
    return con.execute("""
        SELECT inverter_id, opened_on, closed_on, category,
               before_performance_pct, after_performance_pct, delta_pp, outcome
        FROM repair_effectiveness
        WHERE outcome = 'recovered'
          AND before_performance_pct >= 10
          AND category IS NOT NULL
        ORDER BY delta_pp DESC
        LIMIT 1
    """).fetchone()


def plot_example(con, example):
    inverter_id, opened_on, closed_on, category, before_pct, after_pct, delta_pp, outcome = example
    data = con.execute(f"""
        SELECT day,
               100 * actual_clean_kwh / NULLIF(expected_clean_kwh, 0) AS performance_pct
        FROM expected_power
        WHERE inverter_id = ?
          AND day BETWEEN ? - INTERVAL 120 DAY AND ? + INTERVAL 120 DAY
          AND irradiation_coverage >= 0.95
          AND clean_sun_kwh_m2 >= 0.5
          AND NOT anomalous
        ORDER BY day
    """, [inverter_id, opened_on, closed_on]).df()
    data["rolling_14d"] = data["performance_pct"].rolling(14, min_periods=5).median()

    fig, ax = plt.subplots(figsize=(11, 4.8))
    ax.scatter(data["day"], data["performance_pct"], s=10, alpha=0.25,
               color="#4c78a8", label="Valid daily performance")
    ax.plot(data["day"], data["rolling_14d"], color="#1f4e79", linewidth=2,
            label="14-day rolling median")
    ax.axvspan(opened_on, closed_on, color="#f2b134", alpha=0.18,
               label="Ticket open")
    ax.axvline(closed_on, color="#d62728", linestyle="--", linewidth=2,
               label=f"Closed / repair marker: {closed_on}")
    ax.hlines(before_pct, data["day"].min(), opened_on, color="#777777",
              linestyle=":", linewidth=1.5)
    ax.hlines(after_pct, closed_on, data["day"].max(), color="#2ca02c",
              linestyle=":", linewidth=1.5)
    ax.set_ylim(0, max(120, min(160, data["performance_pct"].quantile(0.99) + 10)))
    ax.set_ylabel("Actual / expected (%)")
    ax.set_title(
        f"{inverter_id}: {category} - {outcome} ({before_pct:.1f}% to "
        f"{after_pct:.1f}%, {delta_pp:+.1f} pp)"
    )
    ax.grid(axis="y", alpha=0.2)
    ax.legend(loc="lower right", fontsize=8)
    fig.tight_layout()
    return fig


def validate(con):
    counts = dict(con.execute("""
        SELECT outcome, COUNT(*) FROM repair_effectiveness GROUP BY outcome
    """).fetchall())
    total = sum(counts.values())
    if total < 3:
        raise RuntimeError(f"Expected at least three eligible closed tickets, found {total}")
    if not counts.get("recovered") or not counts.get("worse"):
        raise RuntimeError("Expected both recovered and worse outcomes in real data")
    invalid = con.execute("""
        SELECT COUNT(*) FROM repair_effectiveness
        WHERE outcome <> CASE
          WHEN delta_pp >= 15 THEN 'recovered'
          WHEN delta_pp >= 5 THEN 'partial'
          WHEN delta_pp > -5 THEN 'no-change'
          ELSE 'worse' END
    """).fetchone()[0]
    if invalid:
        raise RuntimeError(f"{invalid} outcome labels do not match their delta")
    print(f"Eligible tickets: {total}; outcomes: {counts}")
    print(con.execute("""
        SELECT inverter_id, opened_on, closed_on, category,
               before_performance_pct, after_performance_pct, delta_pp, outcome
        FROM repair_effectiveness
        ORDER BY delta_pp DESC
    """).df().to_string(index=False))


def main():
    with duckdb.connect(DB_PATH) as con:
        build_table(con)
        validate(con)
        example = pick_example(con)
        if example is None:
            raise RuntimeError("No recovered example is available for plotting")
        fig = plot_example(con, example)
        output = os.path.join(os.path.dirname(DB_PATH), "repair_effectiveness_example.png")
        fig.savefig(output, dpi=150, bbox_inches="tight")
        plt.close(fig)
        print(f"Example chart: {output}")
    print("AI-87 done")


if __name__ == "__main__":
    main()
