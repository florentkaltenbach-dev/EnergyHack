# Module-Type Degradation Comparison

Rebuild with `python analysis/module_types.py`.

The comparison joins each inverter's condition-normalized degradation rate to its
module type. It does not compare raw energy output. Each type reports:

- inverter count and installed capacity;
- median degradation rate;
- interquartile range;
- deterministic bootstrap 95% confidence interval for the median.

Types with fewer than five inverters are marked low confidence. Four categories have
only one inverter, so their zero-width bootstrap intervals describe the observed unit
only and provide no population-level certainty.

The result is descriptive. Module type is confounded with location, inverter group,
maintenance history, and other unmeasured conditions; differences must not be framed
as evidence that a module design caused degradation.
