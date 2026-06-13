# SolarMind Demo Story — INV 01.07.045

## Pitch Hook

> "This inverter passed every PR check in summer 2020 — 93–105 % month after month.
> But vs its own year-1 baseline it had already lost €124 that year.
> By the time the service ticket was opened in October 2020, €403 was gone.
> The ticket stayed open for **4 years and 9 months**.
> Total technical loss over 9.4 years: **€5,309**.
> Not curtailment — proven."

---

## Why This Inverter

INV 01.07.045 is the clearest inverter story in the dataset:

| Criterion | Evidence |
|-----------|----------|
| Looks fine on short-term PR | Summer 2020: 93–105 % monthly PR — passes any 80 % or 85 % threshold |
| Clear degradation vs year-1 baseline | Year-1 (Apr–Sep 2017): **100.4 %**; recent summers 2024–2025: **~82 %** — a **−18 pp** gap |
| NOT curtailment | 94 % of technical loss (€4,969) falls on **uncurtailed days** (DV/EVU = 100) |
| Error-code evidence | 138.8 h — code 0A010A (Netzunterspannung / grid under-voltage, ENS power section); 86.3 h — code 0A0100 (Störmeldung Leistungsteil) |
| Service-ticket evidence | Strangausfall (string failure) ticket open 2020-10-05 to 2025-07-07 — **1,736 days open** |
| Priced loss | €5,309 technical, €320 curtailment; **€4,776 accrued during the exact ticket-open window** |
| Recommended action | Inspect inverter and DC strings (one or more of 5 strings suspected failed) |

---

## Data Provenance & Validated Numbers

All numbers sourced directly from solar.duckdb (9.4-year Plant A dataset).

### Inverter Spec

| Field | Value |
|-------|-------|
| Inverter ID | INV 01.07.045 |
| Rated power | 28.2 kWp |
| Module type | Module Type 11 |
| Number of strings | 5 |

### Performance Ratio vs Own Baseline

| Period | PR |
|--------|----|
| Year-1 baseline (Apr–Sep 2017) | **100.4 %** |
| Summer 2019 average | 99.4 % |
| Summer 2020 average | 99.1 % (passes 80 % threshold — no alert) |
| Summer 2021 average | **77.9 %** (catastrophic drop) |
| Summer 2022 average | 69.7 % |
| Summer 2023 average | 76.6 % |
| Summer 2024 average | 77.4 % |
| Summer 2025 average | 83.7 % |
| 12-month trailing PR (Jul 2025 – Jun 2026) | **89.8 %** |

Degradation rate (OLS on summer months, Apr–Sep): **−2.888 %/year** (R = −0.637, 56 summer months used).

### Annual Loss Attribution

| Year | Actual kWh | Expected kWh | Tech. loss kWh | Tech. loss € | Curt. loss kWh | Curt. loss € |
|------|-----------|--------------|---------------|--------------|----------------|--------------|
| 2017 | 27,952 | 28,483 | 776 | 89 | 0 | 0 |
| 2018 | 31,828 | 31,986 | 704 | 81 | 0 | 0 |
| 2019 | 31,984 | 32,316 | 946 | 109 | 0 | 0 |
| 2020 | 29,961 | 30,488 | 1,082 | 124 | 0 | 0 |
| 2021 | 19,394 | 24,942 | 5,274 | 606 | 8 | 1 |
| 2022 | 21,797 | 31,794 | 9,241 | 2,124 | 391 | 111 |
| 2023 | 22,467 | 29,597 | 6,070 | 701 | 455 | 56 |
| 2024 | 23,952 | 31,271 | 6,701 | 799 | 526 | 63 |
| 2025 | 26,037 | 31,426 | 4,892 | 582 | 394 | 47 |
| 2026 | 10,594 | 12,145 | 790 | 94 | 353 | 42 |
| **Total** | | | **36,476** | **5,309** | **2,127** | **320** |

### Curtailment Separation (key proof)

| Condition | Days | Avg PR | Tech. loss kWh | Tech. loss € |
|-----------|------|--------|---------------|--------------|
| Not curtailed | 2,885 | 87.2 % | 34,666 | 4,969 |
| Curtailed (DV or EVU < 99.5 %) | 99 | 62.1 % | 1,809 | 340 |

**94 % of technical loss occurs on days with no curtailment signal.**
The degradation is genuine, not a grid setpoint artifact.

### Fault-Code Evidence

| Code | Description | Hours logged | First seen | Last seen |
|------|-------------|-------------|-----------|----------|
| 0A010A | Erkennung von Netzunterspannung (ENS, Leistungsteil) | 138.8 h | 2017-03-06 | 2026-05-30 |
| 0A0100 | Störmeldung vom Leistungsteil | 86.3 h | 2017-03-06 | 2026-05-29 |
| 0A0003 | Asymmetrie im Zwischenkreis low | 2.9 h | 2019-08-21 | 2026-04-30 |
| 0A0005 | Absinken pos. Zwischenkreis unter Netzscheitelwert | 0.8 h | 2017-10-29 | 2026-05-29 |

The 0A0003 (DC bus asymmetry) code first fires August 2019 — consistent with a failing string beginning to pull the positive rail.

### Service Ticket Evidence

| Field | Value |
|-------|-------|
| Category | Strangausfall (string failure) |
| Opened | 2020-10-05 |
| Closed | 2025-07-07 |
| Duration | 1,736 days (4 years, 9 months) |
| Loss during exact open window (2020-10-05 to 2025-07-07) | **€4,776 technical loss** |

---

## Lead-Time Analysis

Baseline-comparison detection vs. traditional threshold alert:

| Signal | Date | Method |
|--------|------|--------|
| July 2020: PR = 93.6 % (−6.8 pp vs baseline) | July 2020 | **SolarMind baseline comparison** |
| Service ticket opened | October 2020 | Field inspection |
| Summer 2021: PR = 77.9 % — would trigger 80 % alert | April 2021 | Traditional threshold |

SolarMind surfaces the downward trend **~3 months before the ticket** and **~9 months before a standard 80 % threshold would alarm**.

---

## Slide-Equivalent Summary

### Thesis
A string failure on INV 01.07.045 degraded the inverter by ~20 % of rated output.
Plant-level KPIs and monthly PR checks masked this for years because the inverter was
still "producing something". Comparing each inverter against its own healthy early-life
baseline reveals the loss immediately — and prices it.

### Evidence
- **Year-1 baseline PR: 100.4 %** → **current summer PR: ~82 %** (−18 pp)
- Degradation rate: **−2.9 %/yr** (OLS on 56 summer months, R = −0.64)
- Technical loss: **€5,309 over 9.4 years** (36,476 kWh)
- Curtailment share: **6 %** — the rest is a genuine hardware fault
- Fault codes: DC bus asymmetry (0A0003) from August 2019; power-section faults (0A010A, 0A0100) recurring to 2026
- Service ticket (Strangausfall): open 1,736 days — **€4,776 lost while the ticket sat unresolved**

### Lead-Time
SolarMind detects the anomaly in **July 2020** (−6.8 pp vs baseline).
The service ticket was opened **3 months later** in October 2020 after a field visit.
A standard 80 % threshold alert would not have fired until **April 2021** — 9 months after SolarMind.

### Action
**Inspect inverter and DC strings — one or more of 5 strings suspected failed.**

At current tariff rates, each additional month of inaction costs approximately €48–66 in avoidable technical loss.
Replacement cost for a failed string is typically recovered in under 18 months.
