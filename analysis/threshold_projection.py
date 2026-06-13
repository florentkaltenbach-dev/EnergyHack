"""Linear threshold extrapolation with residual-bootstrap uncertainty."""

import os

import duckdb
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "solar.duckdb")
INVERTER_ID = "INV 01.01.001"
THRESHOLD = 0.80
ORIGIN = pd.Timestamp("2017-04-01")
BOOTSTRAP_SAMPLES = 10_000
RANDOM_SEED = 42


def decimal_years_to_date(values):
    return [ORIGIN + pd.to_timedelta(float(value) * 365.25, unit="D") for value in values]


def fit_projection(con):
    history = con.execute("""
        SELECT month, performance_ratio
        FROM degradation_trend
        WHERE inverter_id = ?
          AND month(month) BETWEEN 4 AND 9
          AND expected_kwh > 50
          AND performance_ratio BETWEEN 0 AND 1.3
        ORDER BY month
    """, [INVERTER_ID]).df()
    x = ((history["month"] - ORIGIN).dt.days / 365.25).to_numpy()
    y = history["performance_ratio"].to_numpy()
    slope, intercept = np.polyfit(x, y, 1)
    fitted = intercept + slope * x
    residuals = y - fitted
    point_crossing = (THRESHOLD - intercept) / slope

    rng = np.random.default_rng(RANDOM_SEED)
    models = []
    crossings = []
    for _ in range(BOOTSTRAP_SAMPLES):
        sample_y = fitted + rng.choice(residuals, size=len(residuals), replace=True)
        sample_slope, sample_intercept = np.polyfit(x, sample_y, 1)
        if sample_slope >= 0:
            continue
        crossing = (THRESHOLD - sample_intercept) / sample_slope
        if crossing <= x.max() or crossing > 30:
            continue
        models.append((sample_slope, sample_intercept))
        crossings.append(crossing)
    if len(crossings) < BOOTSTRAP_SAMPLES * 0.5:
        raise RuntimeError("Too few valid declining bootstrap fits for a useful projection")

    crossing_ci = np.percentile(crossings, [2.5, 50, 97.5])
    point_date = decimal_years_to_date([point_crossing])[0]
    ci_dates = decimal_years_to_date(crossing_ci)
    last_observation = history["month"].max()
    result = pd.DataFrame([{
        "inverter_id": INVERTER_ID,
        "threshold_pct": THRESHOLD * 100,
        "slope_pct_per_year": slope * 100,
        "observations": len(history),
        "last_observation": last_observation.date(),
        "point_crossing_date": point_date.date(),
        "bootstrap_median_crossing_date": ci_dates[1].date(),
        "crossing_ci_low_date": ci_dates[0].date(),
        "crossing_ci_high_date": ci_dates[2].date(),
        "months_from_last_observation": max(
            0, (point_date.year - last_observation.year) * 12
            + point_date.month - last_observation.month
        ),
        "valid_bootstrap_fits": len(crossings),
        "method": "Linear extrapolation of April-September normalized performance",
        "scope": "Scenario extrapolation, not a failure prediction",
    }])
    con.register("threshold_projection_frame", result)
    con.execute("""
        CREATE OR REPLACE TABLE threshold_projection AS
        SELECT inverter_id, ROUND(threshold_pct, 1) AS threshold_pct,
               ROUND(slope_pct_per_year, 3) AS slope_pct_per_year,
               observations, last_observation, point_crossing_date,
               bootstrap_median_crossing_date, crossing_ci_low_date,
               crossing_ci_high_date, months_from_last_observation,
               valid_bootstrap_fits, method, scope
        FROM threshold_projection_frame
    """)
    return history, x, y, slope, intercept, np.asarray(models), crossing_ci


def plot_projection(history, x, y, slope, intercept, models, crossing_ci):
    horizon = min(15.0, max(11.0, crossing_ci[2] + 0.5))
    grid = np.linspace(x.min(), horizon, 300)
    model_values = models[:, 1, None] + models[:, 0, None] * grid[None, :]
    low, median, high = np.percentile(model_values, [2.5, 50, 97.5], axis=0)
    dates = decimal_years_to_date(grid)
    crossing_dates = decimal_years_to_date(crossing_ci)

    fig, ax = plt.subplots(figsize=(11, 5.2))
    ax.scatter(history["month"], y * 100, s=22, alpha=0.6, color="#4c78a8",
               label="Observed summer months")
    ax.plot(dates, (intercept + slope * grid) * 100, color="#1f4e79", linewidth=2,
            label="Linear extrapolation")
    ax.fill_between(dates, low * 100, high * 100, color="#4c78a8", alpha=0.16,
                    label="Residual-bootstrap 95% band")
    ax.axhline(THRESHOLD * 100, color="#d62728", linestyle="--", linewidth=2,
               label="80% action threshold")
    ax.axvspan(crossing_dates[0], crossing_dates[2], color="#d62728", alpha=0.08,
               label="Crossing-date 95% interval")
    ax.axvline(decimal_years_to_date([(THRESHOLD - intercept) / slope])[0],
               color="#d62728", linestyle=":", linewidth=2,
               label="Central crossing estimate")
    ax.set_ylim(40, 115)
    ax.set_ylabel("Actual / expected performance (%)")
    ax.set_title(f"{INVERTER_ID}: extrapolation to 80% of early-life performance")
    ax.grid(axis="y", alpha=0.2)
    ax.legend(loc="lower left", fontsize=8)
    ax.text(0.99, 0.02, "Scenario extrapolation, not a failure prediction",
            transform=ax.transAxes, ha="right", va="bottom", fontsize=9,
            color="#666666", fontstyle="italic")
    fig.tight_layout()
    return fig


def validate(con):
    row = con.execute("SELECT * FROM threshold_projection").df().iloc[0]
    if row.slope_pct_per_year >= 0:
        raise RuntimeError("Selected inverter does not have a declining trend")
    if row.point_crossing_date <= row.last_observation:
        raise RuntimeError("Central crossing estimate is not in the extrapolated future")
    if not (row.crossing_ci_low_date <= row.point_crossing_date <= row.crossing_ci_high_date):
        raise RuntimeError("Central crossing date falls outside bootstrap interval")
    print(row.to_string())


def main():
    with duckdb.connect(DB_PATH) as con:
        history, x, y, slope, intercept, models, crossing_ci = fit_projection(con)
        validate(con)
        fig = plot_projection(history, x, y, slope, intercept, models, crossing_ci)
        output = os.path.join(os.path.dirname(DB_PATH), "threshold_projection.png")
        fig.savefig(output, dpi=150, bbox_inches="tight")
        plt.close(fig)
        print(f"Projection chart: {output}")
    print("AI-90 done")


if __name__ == "__main__":
    main()
