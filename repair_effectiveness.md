# Repair Effectiveness

Rebuild with `python analysis/repair_effectiveness.py`.

The analysis compares normalized performance (`actual_clean_kwh / expected_clean_kwh`)
for the 90 days before ticket opening against the 90 days after ticket closure. The
entire ticket-open period is excluded. Only days with at least 95% irradiation coverage,
at least 0.5 kWh/m2 clean irradiation, and a valid early-life baseline are included.

Outcomes use explicit percentage-point thresholds:

| Outcome | Rule |
|---|---|
| recovered | improvement of at least 15 pp |
| partial | improvement of 5 to less than 15 pp |
| no-change | change within +/-5 pp |
| worse | decline of at least 5 pp |

The generated `repair_effectiveness` table contains every eligible closed ticket and
its sample counts. `repair_effectiveness_example.png` shows the strongest descriptive
recovery with a non-zero pre-ticket baseline: `INV 01.02.012`, whose ticket category is
`Kondensatoren defekt`.

This is a before/after association, not proof that the recorded repair caused the
change. Seasonality is reduced by expected-power normalization, but concurrent field
work and unrecorded interventions remain possible confounders.
