# Degradation Uncertainty

Rebuild with `python analysis/degradation_uncertainty.py`.

Every inverter degradation rate now includes a residual-bootstrap 95% confidence
interval and the number of summer months used. The augmented table is
`degradation_rates_with_uncertainty`; the ranking view is
`v_fix_first_with_uncertainty`.

A rate is visibly marked low confidence when any condition holds:

- fewer than 24 valid summer months;
- the 95% interval crosses zero;
- the interval is wider than 2 percentage points/year.

These intervals quantify uncertainty under the fitted linear residual model. They do
not cover baseline misspecification, unrecorded maintenance, or other structural data
limitations.
