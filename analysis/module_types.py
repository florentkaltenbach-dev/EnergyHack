"""Compare normalized degradation rates by module type with uncertainty."""

import os

import duckdb
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "solar.duckdb")
LOW_CONFIDENCE_N = 5
BOOTSTRAP_SAMPLES = 10_000
RANDOM_SEED = 42


def bootstrap_median_ci(values, rng):
    values = np.asarray(values, dtype=float)
    draws = rng.choice(values, size=(BOOTSTRAP_SAMPLES, len(values)), replace=True)
    medians = np.median(draws, axis=1)
    return np.percentile(medians, [2.5, 97.5])


def build_table(con):
    source = con.execute("""
        SELECT di.module_type, dr.inverter_id, di.kwp,
               dr.degradation_rate_pct_yr
        FROM degradation_rates dr
        JOIN dim_inverters di USING (inverter_id)
        WHERE di.module_type IS NOT NULL
          AND dr.degradation_rate_pct_yr IS NOT NULL
        ORDER BY di.module_type, dr.inverter_id
    """).df()
    rng = np.random.default_rng(RANDOM_SEED)
    rows = []
    for module_type, group in source.groupby("module_type", sort=True):
        rates = group["degradation_rate_pct_yr"].to_numpy()
        ci_low, ci_high = bootstrap_median_ci(rates, rng)
        rows.append({
            "module_type": module_type,
            "inverter_count": len(group),
            "capacity_kwp": group["kwp"].sum(),
            "median_degradation_pct_yr": np.median(rates),
            "q1_pct_yr": np.percentile(rates, 25),
            "q3_pct_yr": np.percentile(rates, 75),
            "bootstrap_ci_low_pct_yr": ci_low,
            "bootstrap_ci_high_pct_yr": ci_high,
            "low_confidence": len(group) < LOW_CONFIDENCE_N,
        })
    summary = pd.DataFrame(rows).sort_values("median_degradation_pct_yr")
    con.register("module_type_summary_frame", summary)
    con.execute("""
        CREATE OR REPLACE TABLE module_type_degradation AS
        SELECT module_type, inverter_count,
               ROUND(capacity_kwp, 1) AS capacity_kwp,
               ROUND(median_degradation_pct_yr, 3) AS median_degradation_pct_yr,
               ROUND(q1_pct_yr, 3) AS q1_pct_yr,
               ROUND(q3_pct_yr, 3) AS q3_pct_yr,
               ROUND(bootstrap_ci_low_pct_yr, 3) AS bootstrap_ci_low_pct_yr,
               ROUND(bootstrap_ci_high_pct_yr, 3) AS bootstrap_ci_high_pct_yr,
               low_confidence,
               CASE WHEN low_confidence
                    THEN 'Low confidence: fewer than 5 inverters'
                    ELSE 'Comparative signal; no causal claim'
               END AS interpretation
        FROM module_type_summary_frame
        ORDER BY median_degradation_pct_yr
    """)


def plot_comparison(con):
    frame = con.execute("SELECT * FROM module_type_degradation ORDER BY median_degradation_pct_yr").df()
    positions = np.arange(len(frame))
    medians = frame["median_degradation_pct_yr"].to_numpy()
    lower = medians - frame["bootstrap_ci_low_pct_yr"].to_numpy()
    upper = frame["bootstrap_ci_high_pct_yr"].to_numpy() - medians
    colors = ["#b0b0b0" if low else "#2f6f9f" for low in frame["low_confidence"]]

    fig, ax = plt.subplots(figsize=(10, 6.5))
    for index, color in enumerate(colors):
        ax.errorbar(medians[index], positions[index],
                    xerr=np.array([[lower[index]], [upper[index]]]),
                    fmt="o", color=color, ecolor=color, markersize=7,
                    elinewidth=2, capsize=4, alpha=0.9)
    ax.axvline(0, color="#555555", linewidth=1, alpha=0.7)
    ax.set_yticks(positions, [
        f"{row.module_type} (n={row.inverter_count})" for row in frame.itertuples()
    ])
    ax.set_xlabel("Median normalized degradation rate (%/year), bootstrap 95% CI")
    ax.set_title("Module-type degradation comparison")
    ax.grid(axis="x", alpha=0.2)
    ax.text(0.99, 0.02, "Grey: low confidence (n < 5)", transform=ax.transAxes,
            ha="right", va="bottom", fontsize=9, color="#666666")
    fig.tight_layout()
    return fig


def validate(con):
    frame = con.execute("SELECT * FROM module_type_degradation").df()
    source_count = con.execute("SELECT COUNT(*) FROM degradation_rates").fetchone()[0]
    if frame["inverter_count"].sum() != source_count:
        raise RuntimeError("Module-type counts do not reconcile to degradation_rates")
    if not (frame.loc[frame["inverter_count"] < LOW_CONFIDENCE_N, "low_confidence"]).all():
        raise RuntimeError("A low-n module type was not marked low confidence")
    if (frame.loc[frame["inverter_count"] >= LOW_CONFIDENCE_N, "low_confidence"]).any():
        raise RuntimeError("A sufficiently sampled module type was marked low confidence")
    if (frame["bootstrap_ci_low_pct_yr"] > frame["median_degradation_pct_yr"]).any():
        raise RuntimeError("A bootstrap lower bound exceeds its median")
    if (frame["bootstrap_ci_high_pct_yr"] < frame["median_degradation_pct_yr"]).any():
        raise RuntimeError("A bootstrap upper bound is below its median")
    print(frame.to_string(index=False))
    print(f"Counts reconcile: {source_count} inverters; low-confidence threshold n < {LOW_CONFIDENCE_N}")


def main():
    with duckdb.connect(DB_PATH) as con:
        build_table(con)
        validate(con)
        fig = plot_comparison(con)
        output = os.path.join(os.path.dirname(DB_PATH), "module_type_degradation.png")
        fig.savefig(output, dpi=150, bbox_inches="tight")
        plt.close(fig)
        print(f"Comparison chart: {output}")
    print("AI-89 done")


if __name__ == "__main__":
    main()
