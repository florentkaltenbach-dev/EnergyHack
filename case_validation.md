# SolarMind Case Validation

Rebuild with `python analysis/validate_cases.py`. The source-of-truth output is the
`validation_cases` table in `solar.duckdb`; this note records the selection logic.

## Reconciled Cases

| Inverter | Role | Why selected |
|---|---|---|
| INV 01.07.045 | Hero | String-failure ticket, early detection story, and priced technical loss |
| INV 01.07.047 | Additional case | 12.6 pp recent summer gap, translated fault evidence, and a string-failure ticket |
| INV 01.08.057 | Additional case | 32 pp recent summer gap and a ticket reporting multiple defective boards |

For every row, the script checks that the long-term degradation rate is present,
recent annual technical loss traces to `revenue_loss`, the top fault traces to
`fault_events` and `dim_error_desc`, and curtailment is less than 10% of combined
technical-plus-curtailment loss.

## Rejected Candidate

`INV 01.05.034` was screened and excluded. Its degradation trend is weak
(-0.203%/yr), while curtailment accounts for 33.6% of combined priced technical and
curtailment loss. It does not support a clean hardware-degradation case.

## Interpretation

The hero case is not isolated: two additional inverters reconcile end to end with
large recent summer performance gaps, low curtailment shares, priced technical loss,
and independent operational evidence. These are historical associations, not failure
predictions or causal claims about a specific component.
