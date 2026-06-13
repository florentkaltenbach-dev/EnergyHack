"""Attach residual-bootstrap confidence intervals to inverter degradation rates."""

import os

import duckdb
import numpy as np
import pandas as pd

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "solar.duckdb")
BOOTSTRAP_SAMPLES = 5_000
RANDOM_SEED = 42
MIN_MONTHS = 24
MAX_CI_WIDTH_PCT_YR = 2.0


def bootstrap_slope_ci(x, y, rng):
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    x_centered = x - x.mean()
    slope = np.sum(x_centered * (y - y.mean())) / np.sum(x_centered ** 2)
    intercept = y.mean() - slope * x.mean()
    fitted = intercept + slope * x
    residuals = y - fitted
    sampled = rng.choice(residuals, size=(BOOTSTRAP_SAMPLES, len(y)), replace=True)
    bootstrap_y = fitted[None, :] + sampled
    bootstrap_slopes = np.sum(
        x_centered[None, :] * (bootstrap_y - bootstrap_y.mean(axis=1, keepdims=True)),
        axis=1,
    ) / np.sum(x_centered ** 2)
    low, high = np.percentile(bootstrap_slopes * 100, [2.5, 97.5])
    return slope * 100, low, high


def build_table(con):
    source = con.execute("""
        SELECT inverter_id, month, performance_ratio,
               date_diff('day', DATE '2017-07-01', month) / 365.25 AS years_since_baseline
        FROM degradation_trend
        WHERE month(month) BETWEEN 4 AND 9
          AND expected_kwh > 50
          AND performance_ratio BETWEEN 0 AND 1.3
        ORDER BY inverter_id, month
    """).df()
    rng = np.random.default_rng(RANDOM_SEED)
    rows = []
    for inverter_id, group in source.groupby("inverter_id", sort=True):
        if len(group) < 12:
            continue
        rate, ci_low, ci_high = bootstrap_slope_ci(
            group["years_since_baseline"].to_numpy(),
            group["performance_ratio"].to_numpy(),
            rng,
        )
        ci_width = ci_high - ci_low
        reasons = []
        if len(group) < MIN_MONTHS:
            reasons.append(f"fewer than {MIN_MONTHS} summer months")
        if ci_low <= 0 <= ci_high:
            reasons.append("95% interval crosses zero")
        if ci_width > MAX_CI_WIDTH_PCT_YR:
            reasons.append(f"CI wider than {MAX_CI_WIDTH_PCT_YR:.1f} pp/year")
        rows.append({
            "inverter_id": inverter_id,
            "degradation_rate_pct_yr": rate,
            "ci_low_pct_yr": ci_low,
            "ci_high_pct_yr": ci_high,
            "ci_width_pct_yr": ci_width,
            "sample_months": len(group),
            "low_confidence": bool(reasons),
            "confidence_reason": "; ".join(reasons) if reasons else "Interval excludes zero and is sufficiently narrow",
        })
    frame = pd.DataFrame(rows)
    con.register("degradation_uncertainty_frame", frame)
    con.execute("""
        CREATE OR REPLACE TABLE degradation_rates_with_uncertainty AS
        SELECT u.inverter_id,
               ROUND(u.degradation_rate_pct_yr, 3) AS degradation_rate_pct_yr,
               ROUND(u.ci_low_pct_yr, 3) AS ci_low_pct_yr,
               ROUND(u.ci_high_pct_yr, 3) AS ci_high_pct_yr,
               ROUND(u.ci_width_pct_yr, 3) AS ci_width_pct_yr,
               u.sample_months, u.low_confidence, u.confidence_reason,
               d.trend_correlation, d.technical_lost_kwh
        FROM degradation_uncertainty_frame u
        JOIN degradation_rates d USING (inverter_id)
        ORDER BY degradation_rate_pct_yr
    """)
    con.execute("""
        CREATE OR REPLACE VIEW v_fix_first_with_uncertainty AS
        SELECT f.*, u.ci_low_pct_yr, u.ci_high_pct_yr, u.sample_months,
               u.low_confidence, u.confidence_reason
        FROM v_fix_first f
        LEFT JOIN degradation_rates_with_uncertainty u USING (inverter_id)
        ORDER BY f.avoidable_loss_eur DESC
    """)


def validate(con):
    frame = con.execute("SELECT * FROM degradation_rates_with_uncertainty").df()
    expected = con.execute("SELECT COUNT(*) FROM degradation_rates").fetchone()[0]
    if len(frame) != expected:
        raise RuntimeError(f"Expected uncertainty for {expected} rates, found {len(frame)}")
    if frame[["ci_low_pct_yr", "ci_high_pct_yr", "sample_months"]].isna().any().any():
        raise RuntimeError("A degradation rate is missing CI or sample count")
    if not ((frame["ci_low_pct_yr"] <= frame["degradation_rate_pct_yr"])
            & (frame["degradation_rate_pct_yr"] <= frame["ci_high_pct_yr"])).all():
        raise RuntimeError("A point estimate lies outside its interval")
    print(frame[[
        "inverter_id", "degradation_rate_pct_yr", "ci_low_pct_yr",
        "ci_high_pct_yr", "sample_months", "low_confidence", "confidence_reason"
    ]].to_string(index=False))
    print(f"Rates with uncertainty: {len(frame)}; low confidence: {int(frame.low_confidence.sum())}")


def main():
    with duckdb.connect(DB_PATH) as con:
        build_table(con)
        validate(con)
    print("AI-92 done")


if __name__ == "__main__":
    main()
