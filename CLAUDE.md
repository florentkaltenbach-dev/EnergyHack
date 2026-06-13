# SolarMind 2 — Claude Code instructions

## Project
AI chatbot (LangGraph text-to-SQL agent + Streamlit UI) over 9.4 years of Plant A solar
monitoring data. Track: Enerparc open track, Energy/AI Hackathon Munich.

Thesis: per-inverter degradation is hidden by plant-level KPIs. Surface it, price it in €,
prove it isn't curtailment, explain with error codes + tickets, recommend action.

## Paths
- Repo / working dir: `D:\EnergyHack\solar-mind2\`
- Database: `solar.duckdb` (in repo root, gitignored)
- Raw data: `data/` (parquet + xlsx files, gitignored)
- Rebuild DB: `python db/loader.py` (~50 s)

## Stack
- Python + DuckDB (embedded)
- LangGraph agent, `langchain-groq`, model `llama-3.3-70b-versatile`
- `GROQ_API_KEY` in `.env` (gitignored)
- Streamlit UI (`app/`)
- `pvlib` available if needed

## Linear sync (REQUIRED)
Project: **"Enerparc Open Track (Plant A)"**, team **AI Kanban Pilot**.
Available states for this team: `Backlog` · `Spec'd` · `Working` · `Review` · `Done`

**When you start a milestone → set its Linear issue to `Working`.**
**When you finish a milestone → set its Linear issue to `Done`.**

Use `mcp__claude_ai_Linear__save_issue` with the issue `id` (e.g. `"AI-76"`) and `state` field.
Do not skip this — it is the only way the team can follow progress.

Milestone map:
- AI-75  M0  Toolchain commit & de-risk                   → Done
- AI-76  M1  Data spine (schema, joins, DuckDB tables)    → Working
- AI-77  M2  Healthy year-1 expected-power baseline
- AI-78  M3  Degradation, incidents & curtailment exclusion
- AI-79  M4  Financial attribution (lost kWh → €)
- AI-80  M5  Error-code + ticket evidence                 (EDGE/stretch)
- AI-81  M6  Thin decision agent                          (EDGE/stretch)
- AI-82  M7  Thin two-page Streamlit dashboard
- AI-83  M8  Demo discipline & pitch

## Database schema (read schema.txt for full detail)
```
fact_power      64M rows   ts | inverter_id | p_ac_kw | i_dc_a | u_dc_v
fact_plant      990k rows  ts | irradiation_wm2 | altitude_deg | dv_pct | evu_pct | ...
fault_events    439k rows  ts | inverter_id | error_code | op_state
dim_inverters   65 rows    inverter_id | kwp | module_type | n_strings | ...
dim_error_desc  65 rows    error_code | description
dim_tariff      37k rows   inverter_id | week_start | tariff_ct_kwh (EUROcent/kWh)
tickets_recent  73 rows    2020-2026 service tickets
tickets_legacy  11 rows    2019-2020 service tickets

Views: v_inverter_month_pr · v_inverter_day_pr · v_inverter_summary
```

## Critical formulas
- Energy:      `kWh = SUM(p_ac_kw) / 12.0`  (5-min intervals, NOT /60)
- Revenue:     `€ = kwh * tariff_ct_kwh / 100.0`  (tariff in EUROcent)
- Daytime:     `fact_plant.altitude_deg > 0`
- Curtailment: DV/EVU are allowed-power setpoints. `100` = unrestricted; a non-null
               value below `99.5` means curtailed. These are NOT faults.
- Downtime:    `COUNT(fault_events rows) * 5 / 60` = hours

## Key data gotchas
- Inverter IDs: `INV 01.01.001` format (plant.group.unit) — already normalised in DB
- Year 1 (2016-12-31 → end of 2017) is NOT fully healthy: exclude commissioning ramp-up
  and obvious outages before baselining. Use 2017-04-01 to 2017-09-30 as baseline window.
- dv_pct / evu_pct are allowed-power percentages, not percent curtailed. Treat values
  below `99.5` as curtailed; null means the control signal was unavailable.
- Tariff is in EUROcent/kWh (divide by 100 to get €)
- Minimum irradiation filter: 50 W/m² for daytime analysis

## DB access
```python
from db.db import run_query, get_schema
df = run_query("SELECT * FROM dim_inverters LIMIT 5")
```
