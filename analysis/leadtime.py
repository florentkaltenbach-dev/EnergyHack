"""Lead-time vs ticket analysis and timeline chart — AI-85.

Finds the first detector-flag date for each incident run (contiguous days
in incident_flags where performance fell below 70 %), then joins to:
  - fault_events  → first error-code timestamp after the flag
  - tickets_recent → first ticket opened after the flag

Produces lead_time_matches TABLE and a matplotlib timeline figure for the
single cleanest example (flag strictly precedes both error code and ticket).
"""

import os
import duckdb
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "solar.duckdb")


def build_tables(con):
    con.execute("""
        CREATE OR REPLACE TABLE lead_time_matches AS
        WITH non_curtailed AS (
            -- Only non-curtailed incident days: genuine technical drops, not grid constraints
            SELECT inverter_id, day
            FROM incident_flags
            WHERE NOT curtailed
        ), flagged AS (
            SELECT inverter_id, day,
                   LAG(day) OVER (PARTITION BY inverter_id ORDER BY day) AS prev_day
            FROM non_curtailed
        ), incident_starts AS (
            -- New incident when gap > 3 days (tolerates weekend gaps in 5-min data)
            SELECT inverter_id, day AS incident_start
            FROM flagged
            WHERE prev_day IS NULL
               OR date_diff('day', prev_day, day) > 3
        ), first_error AS (
            SELECT i.inverter_id, i.incident_start,
                   (MIN(fe.ts))::DATE AS first_error_date
            FROM incident_starts i
            JOIN fault_events fe
              ON fe.inverter_id = i.inverter_id
             AND fe.ts::DATE > i.incident_start
             AND fe.ts::DATE <= i.incident_start + INTERVAL 90 DAY
            GROUP BY 1, 2
        ), first_ticket AS (
            SELECT i.inverter_id, i.incident_start,
                   MIN(TRY_CAST(t.startdate AS TIMESTAMPTZ))::DATE AS ticket_opened
            FROM incident_starts i
            JOIN tickets_recent t
              ON t.component = i.inverter_id
             AND TRY_CAST(t.startdate AS TIMESTAMPTZ)::DATE
                 BETWEEN i.incident_start
                     AND i.incident_start + INTERVAL 180 DAY
            GROUP BY 1, 2
        )
        SELECT i.inverter_id,
               i.incident_start,
               e.first_error_date,
               tk.ticket_opened,
               date_diff('day', i.incident_start, e.first_error_date)  AS days_to_error,
               date_diff('day', i.incident_start, tk.ticket_opened)    AS days_to_ticket
        FROM incident_starts i
        LEFT JOIN first_error  e  USING (inverter_id, incident_start)
        LEFT JOIN first_ticket tk USING (inverter_id, incident_start)
        WHERE e.first_error_date IS NOT NULL OR tk.ticket_opened IS NOT NULL
        ORDER BY i.inverter_id, i.incident_start
    """)


def print_stats(con):
    row = con.execute("""
        SELECT COUNT(*)                                                  AS n_matched,
               COUNT(days_to_ticket)                                     AS n_with_ticket,
               COUNT(days_to_error)                                      AS n_with_error,
               ROUND(MEDIAN(days_to_ticket), 0)                         AS med_days_ticket,
               ROUND(MEDIAN(days_to_error),  0)                         AS med_days_error,
               MIN(days_to_ticket)                                       AS min_ticket,
               MAX(days_to_ticket)                                       AS max_ticket
        FROM lead_time_matches
    """).fetchone()
    n, n_tk, n_err, med_tk, med_err, mn, mx = row
    print(f"Matched incidents : {n} total  |  {n_tk} with ticket  |  {n_err} with error code")
    print(f"Flag->ticket      : median {med_tk} days  (range {mn}-{mx})")
    print(f"Flag->error code  : median {med_err} days")
    assert n_tk >= 3, f"Need >=3 ticket-matched incidents for AI-85, got {n_tk}"
    print(">=3 matched incidents OK")
    return dict(n_matched=n, n_with_ticket=n_tk, n_with_error=n_err,
                med_days_ticket=med_tk, med_days_error=med_err)


def pick_example(con):
    """Cleanest example: flag before both error code AND ticket, largest ticket gap."""
    row = con.execute("""
        SELECT inverter_id,
               incident_start::VARCHAR   AS incident_start,
               first_error_date::VARCHAR AS first_error_date,
               ticket_opened::VARCHAR    AS ticket_opened,
               days_to_error,
               days_to_ticket
        FROM lead_time_matches
        WHERE days_to_ticket > 0
          AND days_to_error  > 0
          AND days_to_ticket > days_to_error
        ORDER BY days_to_ticket DESC
        LIMIT 1
    """).fetchone()
    if row is None:
        # Fallback: any incident with a positive ticket lead-time
        row = con.execute("""
            SELECT inverter_id,
                   incident_start::VARCHAR,
                   first_error_date::VARCHAR,
                   ticket_opened::VARCHAR,
                   days_to_error,
                   days_to_ticket
            FROM lead_time_matches
            WHERE days_to_ticket > 0
            ORDER BY days_to_ticket DESC
            LIMIT 1
        """).fetchone()
    return row


def plot_timeline(example):
    """Return a matplotlib Figure: detector-flag → error-code → ticket timeline."""
    inv, flag_date, error_date, ticket_date, d_error, d_ticket = example

    fig, ax = plt.subplots(figsize=(10, 2.8))
    ax.set_xlim(-8, d_ticket + 25)
    ax.set_ylim(0, 1)
    ax.axis("off")
    fig.patch.set_facecolor("#fafafa")

    # Spine
    ax.plot([0, d_ticket], [0.5, 0.5], color="#cccccc", lw=2, zorder=1)

    events = []
    events.append((0, "#2ecc71", f"Detector flag\n{flag_date}"))
    if error_date and d_error is not None:
        events.append((d_error, "#f39c12", f"First error code\n+{d_error} d  ({error_date})"))
    if ticket_date and d_ticket is not None:
        events.append((d_ticket, "#e74c3c", f"Ticket opened\n+{d_ticket} d  ({ticket_date})"))

    for x, color, label in events:
        ax.scatter(x, 0.5, s=160, color=color, zorder=3, edgecolors="white", linewidths=1.5)
        ax.text(x, 0.76, label, ha="center", va="bottom", fontsize=8.5,
                color="#333333", linespacing=1.4)

    # Lead-time brace
    if d_ticket:
        ax.annotate("", xy=(d_ticket, 0.24), xytext=(0, 0.24),
                    arrowprops=dict(arrowstyle="<->", color="#555555", lw=1.3))
        ax.text(d_ticket / 2, 0.10,
                f"SolarMind flagged {d_ticket} days before ticket",
                ha="center", va="center", fontsize=9.5,
                color="#555555", fontstyle="italic", fontweight="bold")

    ax.set_title(f"{inv}  —  early-warning lead-time example",
                 fontsize=10, pad=10, color="#222222")
    fig.tight_layout(pad=0.5)
    return fig


def main():
    with duckdb.connect(DB_PATH) as con:
        build_tables(con)
        print_stats(con)
        example = pick_example(con)
        if example:
            fig = plot_timeline(example)
            out = os.path.join(os.path.dirname(DB_PATH), "lead_time_example.png")
            fig.savefig(out, dpi=150, bbox_inches="tight")
            plt.close(fig)
            print(f"Timeline saved: {out}")
            inv, flag, err, tk, d_err, d_tk = example
            print(f"Example: {inv}  flag {flag} -> error {err} (+{d_err}d) -> ticket {tk} (+{d_tk}d)")
        else:
            print("No clean example found where flag precedes both error code and ticket.")
    print("AI-85 done")


if __name__ == "__main__":
    main()
