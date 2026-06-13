# What This Proves - and What Comes Next

**LIVE Q&A BACKUP ONLY - NOT IN VIDEO**

## Deliberate Scope Cut

- **Plant A only:** Plant B was excluded to protect end-to-end validation quality.
- **No failure prediction:** SolarMind surfaces historical degradation patterns and
  threshold scenarios; it does not claim a future component failure date.
- **Thin decision agent:** the agent ranks and explains validated table values. It is
  not a general-purpose chatbot and cannot invent diagnoses or financial figures.

## Known Caveats

- **Partial service history:** supplied tickets are sparse and do not capture every
  intervention, so ticket associations are evidence, not complete ground truth.
- **Early-life baseline assumptions:** expected power uses clean April-September 2017
  behavior and physics-lite irradiance normalization because tilt, azimuth, and full
  equipment parameters are unavailable.
- **Single-plant evidence:** module-type and group comparisons are descriptive and
  confounded by location, maintenance, and operating conditions; they are not causal.
- **Uncertain trend estimates:** 37 of 55 inverter degradation rates have wide or
  zero-crossing confidence intervals and are explicitly marked low confidence.

## Concrete Next Steps

1. **Prospective shadow trial:** run SolarMind alongside current O&M triage for 8-12
   weeks and measure alert precision, technician acceptance, and days of lead time.
2. **Close the maintenance loop:** capture structured repair action, component changed,
   labor cost, and post-repair verification so repair effectiveness becomes causal-grade.
3. **Cross-plant validation:** rebuild the baseline on Plant B and additional sites,
   then test whether ranking quality and module/group patterns generalize.
4. **Calibrate decision thresholds:** set action floors and confidence requirements with
   Enerparc engineers using warranty terms, inspection cost, and recoverable EUR/year.
