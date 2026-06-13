# Forward Projection to Threshold

Rebuild with `python analysis/threshold_projection.py`.

The example uses `INV 01.01.001` and an explicit action threshold of 80% of the
inverter's own early-life expected performance. A linear trend is fitted only to valid
April-September monthly normalized performance. Residual bootstrap resampling provides
a 95% uncertainty band for the trend and threshold-crossing date.

The central linear extrapolation crosses the threshold around July 2027, roughly 13
months after the last observation in June 2026. The bootstrap interval is deliberately
shown because the crossing date is sensitive to month-to-month variation and the
assumption that the historical linear trend continues.

This is a scenario extrapolation for maintenance planning, not a failure prediction,
warranty determination, or claim that performance will continue linearly.
