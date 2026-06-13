"""Detect combiner groups drifting materially worse than the fleet."""

import os

import duckdb
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "solar.duckdb")
MIN_MEMBER_GAP_PP = -10.0
MIN_MEMBER_SHARE = 0.60
MIN_WORSE_THAN_FLEET_PP = 5.0


def build_tables(con):
    con.execute("""
        CREATE OR REPLACE TABLE group_residual_monthly AS
        SELECT split_part(inverter_id, '.', 2) AS group_id,
               month,
               COUNT(*) AS member_count,
               ROUND(MEDIAN((performance_ratio - 1) * 100), 2) AS median_residual_pct,
               ROUND(AVG((performance_ratio - 1) * 100), 2) AS mean_residual_pct
        FROM degradation_trend
        WHERE performance_ratio IS NOT NULL
        GROUP BY 1, 2
        ORDER BY 1, 2
    """)
    con.execute(f"""
        CREATE OR REPLACE TABLE group_drift_summary AS
        WITH inverter_gaps AS (
            SELECT inverter_id,
                   split_part(inverter_id, '.', 2) AS group_id,
                   100 * (
                     AVG(performance_ratio) FILTER (
                       WHERE month >= DATE '2024-04-01'
                         AND month < DATE '2026-01-01'
                         AND month(month) BETWEEN 4 AND 9
                     ) -
                     AVG(performance_ratio) FILTER (
                       WHERE month >= DATE '2017-04-01'
                         AND month < DATE '2017-10-01'
                     )
                   ) AS summer_gap_pp
            FROM degradation_trend
            GROUP BY 1, 2
        ), fleet AS (
            SELECT MEDIAN(summer_gap_pp) AS fleet_median_gap_pp
            FROM inverter_gaps
        ), grouped AS (
            SELECT group_id, COUNT(*) AS member_count,
                   MEDIAN(summer_gap_pp) AS group_median_gap_pp,
                   AVG(summer_gap_pp) AS group_mean_gap_pp,
                   AVG((summer_gap_pp <= {MIN_MEMBER_GAP_PP})::INTEGER) AS member_share_down,
                   MIN(summer_gap_pp) AS worst_member_gap_pp,
                   MAX(summer_gap_pp) AS best_member_gap_pp
            FROM inverter_gaps
            GROUP BY 1
        )
        SELECT g.group_id, g.member_count,
               ROUND(g.group_median_gap_pp, 1) AS group_median_gap_pp,
               ROUND(g.group_mean_gap_pp, 1) AS group_mean_gap_pp,
               ROUND(f.fleet_median_gap_pp, 1) AS fleet_median_gap_pp,
               ROUND(g.group_median_gap_pp - f.fleet_median_gap_pp, 1) AS versus_fleet_pp,
               ROUND(100 * g.member_share_down, 0) AS members_down_10pp_pct,
               ROUND(g.worst_member_gap_pp, 1) AS worst_member_gap_pp,
               ROUND(g.best_member_gap_pp, 1) AS best_member_gap_pp,
               g.group_median_gap_pp <= f.fleet_median_gap_pp - {MIN_WORSE_THAN_FLEET_PP}
                 AND g.member_share_down >= {MIN_MEMBER_SHARE} AS group_flag,
               CASE
                 WHEN g.group_median_gap_pp <= f.fleet_median_gap_pp - {MIN_WORSE_THAN_FLEET_PP}
                   AND g.member_share_down >= {MIN_MEMBER_SHARE}
                   THEN 'Group-wide drift: investigate shared AC-side, sensor, or environmental cause'
                 ELSE 'No group-wide flag: inspect member inverters individually'
               END AS interpretation
        FROM grouped g CROSS JOIN fleet f
        ORDER BY group_median_gap_pp
    """)


def plot_heatmap(con):
    frame = con.execute("""
        SELECT group_id, year(month) AS yr, MEDIAN(median_residual_pct) AS residual_pct
        FROM group_residual_monthly
        WHERE month(month) BETWEEN 4 AND 9
          AND year(month) <= 2025
        GROUP BY 1, 2
        ORDER BY 1, 2
    """).df()
    groups = sorted(frame["group_id"].unique())
    years = sorted(frame["yr"].unique())
    matrix = np.full((len(groups), len(years)), np.nan)
    for row in frame.itertuples():
        matrix[groups.index(row.group_id), years.index(row.yr)] = row.residual_pct

    fig, ax = plt.subplots(figsize=(11, 5.2))
    image = ax.imshow(matrix, aspect="auto", cmap="RdYlGn", vmin=-40, vmax=10)
    ax.set_xticks(range(len(years)), years)
    ax.set_yticks(range(len(groups)), [f"Group {group}" for group in groups])
    ax.set_title("Combiner-group summer residual vs own early-life baseline")
    ax.set_xlabel("Year (April-September median)")
    ax.set_ylabel("GG group")
    for row_index in range(len(groups)):
        for column_index in range(len(years)):
            value = matrix[row_index, column_index]
            if not np.isnan(value):
                ax.text(column_index, row_index, f"{value:.0f}", ha="center", va="center",
                        fontsize=7, color="black" if value > -25 else "white")
    colorbar = fig.colorbar(image, ax=ax, pad=0.02)
    colorbar.set_label("Median residual (%)")
    fig.tight_layout()
    return fig


def validate(con):
    flagged = con.execute("""
        SELECT * FROM group_drift_summary WHERE group_flag ORDER BY group_id
    """).df()
    if flagged.empty:
        raise RuntimeError("Expected at least one group materially worse than the fleet")
    if not ((flagged["members_down_10pp_pct"] >= 60).all()
            and (flagged["versus_fleet_pp"] <= -5).all()):
        raise RuntimeError("A group flag does not satisfy the documented thresholds")
    hero_group = con.execute("""
        SELECT group_flag, versus_fleet_pp
        FROM group_drift_summary WHERE group_id = '07'
    """).fetchone()
    if hero_group is None or hero_group[0]:
        raise RuntimeError("Hero inverter group 07 must remain an unflagged single-inverter case")
    print("Flagged groups:")
    print(flagged.to_string(index=False))
    print(f"\nHero group 07: not flagged; versus fleet = {hero_group[1]:+.1f} pp")


def main():
    with duckdb.connect(DB_PATH) as con:
        build_tables(con)
        validate(con)
        fig = plot_heatmap(con)
        output = os.path.join(os.path.dirname(DB_PATH), "group_drift_heatmap.png")
        fig.savefig(output, dpi=150, bbox_inches="tight")
        plt.close(fig)
        print(f"Heatmap: {output}")
    print("AI-88 done")


if __name__ == "__main__":
    main()
