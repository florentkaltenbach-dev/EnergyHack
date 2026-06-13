# Combiner Group Drift

Rebuild with `python analysis/group_drift.py`.

The `GG` segment of each inverter ID defines its group. Monthly group residual is the
median inverter performance relative to each inverter's own early-life expected power.

A group is flagged only when both conditions hold:

1. Its 2024-2025 summer median gap is at least 5 percentage points worse than the
   fleet-wide inverter median gap.
2. At least 60% of its members have declined by 10 percentage points or more.

Groups `03` and `08` satisfy both tests. Every member in each group declined by at
least 10 percentage points, and their median gaps are 6-7 points worse than the fleet.
This is consistent with a shared group-level issue worth investigating, but it does
not identify a specific AC-side, sensor, or environmental cause.

The known single-inverter hero case `INV 01.07.045` belongs to group `07`. Group `07`
is not flagged and performs 2.4 percentage points better than the fleet median gap.
This prevents the individual string-failure story from being misclassified as a
group-wide fault.
