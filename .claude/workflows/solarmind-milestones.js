export const meta = {
  name: 'solarmind-milestones',
  description: 'Master agent: implement SolarMind milestones sequentially, one fresh subagent per milestone',
  phases: [
    { title: 'M1 Data spine' },
    { title: 'M2 Baseline' },
    { title: 'M3 Degradation' },
    { title: 'M4 Financials' },
    { title: 'M7 Dashboard' },
    { title: 'M8 Demo' },
  ],
}

const WORKDIR = 'D:\\EnergyHack\\solar-mind2'

const MILESTONES = [
  {
    linearId: 'AI-76',
    phase: 'M1 Data spine',
    title: 'M1 · Data spine (schema, joins, DuckDB tables)',
    context: `
The DB schema and loader (db/loader.py) are already complete and solar.duckdb exists.
verify_m1.py is written. Your job for M1:
1. Run verify_m1.py and check all assertions pass.
2. If any fail, fix the underlying issue in db/loader.py or db/db.py and re-run.
3. Once all checks pass, M1 is done.
Do NOT rewrite the loader from scratch — it is correct. Only fix what verify_m1.py flags.`,
  },
  {
    linearId: 'AI-77',
    phase: 'M2 Baseline',
    title: 'M2 · Healthy year-1 expected-power baseline',
    context: `
analysis/baseline.py is written. It computes per-inverter baseline PR from clean year-1 data
(2017-04-01 to 2017-09-30) and writes baseline_pr + expected_power tables to solar.duckdb.
Your job for M2:
1. Run: python analysis/baseline.py
2. Check output looks sane (avg baseline PR ~ 0.7–0.9, top-10 underperformers printed).
3. Fix any runtime errors.
4. Confirm expected_power has ~220k rows (one row per inverter per day).
CURTAILMENT NOTE: DV/EVU are allowed-power setpoints. 100 means unrestricted;
a non-null value below 99.5 means curtailed. The baseline already filters these.`,
  },
  {
    linearId: 'AI-78',
    phase: 'M3 Degradation',
    title: 'M3 · Degradation, incidents & curtailment exclusion',
    context: `
analysis/degradation.py may already exist. Your job for M3:
1. Read what exists in analysis/degradation.py.
2. Implement or complete degradation analysis:
   - Rolling residual trend per inverter across all years → degradation rate (%/yr)
   - Rank inverters by degradation severity
   - Short-horizon incidents: flag inverter-days where actual < 70% of expected (non-curtailed)
   - Curtailment exclusion: non-null dv_pct < 99.5 OR evu_pct < 99.5 means curtailed, never a fault
   - Write results to solar.duckdb: degradation_trend table + incident_flags table
3. Print top-5 most degraded inverters with rate and total lost kWh.
Prerequisite: expected_power table must exist (M2 must be done first).`,
  },
  {
    linearId: 'AI-79',
    phase: 'M4 Financials',
    title: 'M4 · Financial attribution (lost kWh → €)',
    context: `
analysis/financials.py may already exist. Your job for M4:
1. Read what exists in analysis/financials.py.
2. Implement or complete financial attribution:
   - lost_kwh = max(expected_kwh - actual_kwh, 0) per inverter per day (from expected_power)
   - Revenue loss = lost_kwh × tariff_ct_kwh / 100 (join dim_tariff on week_start)
   - Split into buckets: avoidable-technical / curtailment / weather-uncertain
   - Only avoidable (+ soiling) → "Fix First" priority; curtailment shown separately
   - Write financial_loss table to solar.duckdb
   - Print Fix First ranking: top inverters by total avoidable € loss
3. Sanity check: total avoidable loss should be a plausible fraction of total potential revenue.
Prerequisite: expected_power + degradation_trend tables must exist (M2+M3 done).`,
  },
  {
    linearId: 'AI-82',
    phase: 'M7 Dashboard',
    title: 'M7 · Thin two-page Streamlit dashboard',
    context: `
Build a thin Streamlit app in app/. Two pages:
PAGE 1 — Overview:
  - Plant health summary (total kWh, avg PR, total fault hours)
  - Fix First table: inverters ranked by avoidable € loss (from financial_loss table)
  - Curtailment shown separately (not mixed into Fix First)

PAGE 2 — Inverter detail (select from sidebar):
  - Early-life baseline PR vs current rolling PR (line chart)
  - Total degradation (%/yr) and lifetime lost kWh
  - Error code history (bar chart by code, hours)
  - Relevant tickets

Keep it simple — working beats polished. Use st.cache_data for all DB queries.
DB access: from db.db import run_query
Prerequisite: all analytics tables from M2–M4 must exist.`,
  },
  {
    linearId: 'AI-83',
    phase: 'M8 Demo',
    title: 'M8 · Demo discipline & pitch',
    context: `
Pick ONE real inverter story for the demo:
- An inverter that looks fine on short-term / PR metrics
- But shows clear degradation vs its own year-1 baseline
- Confirmed NOT curtailment (separate the loss)
- Has error code / ticket evidence
- Has a priced loss in € and a recommended action

Deliverables:
1. Identify the best demo inverter (query the DB) and document it in a file demo_story.md
2. Replace every placeholder in the dashboard with real, validated numbers for this inverter
3. Write the pitch hook: "This inverter passes PR checks — but it's lost €X over N years"
4. Add one slide-equivalent summary section to demo_story.md: thesis, evidence, lead-time, action`,
  },
]

// Run milestones sequentially — each depends on the previous
for (const m of MILESTONES) {
  phase(m.phase)

  const result = await agent(
    `You are implementing the SolarMind hackathon project (Enerparc open track).
Working directory: ${WORKDIR}

YOUR TASK: ${m.linearId} — ${m.title}

FIRST: Read CLAUDE.md in the working directory for full project context, schema, and Linear sync instructions.

THEN: Mark this issue as Working in Linear using mcp__claude_ai_Linear__save_issue with id="${m.linearId}" and state="Working".

TASK-SPECIFIC CONTEXT:
${m.context}

WHEN DONE: Mark ${m.linearId} as Done in Linear (state="Done").

Rules:
- Do not implement the next milestone — stop when this one is verified and Linear is updated.
- If something is already correctly implemented, verify it, mark Done, and stop.
- Use python to run scripts and verify output. Fix errors until checks pass.
- Keep code clean and consistent with what already exists.`,
    { label: m.linearId, phase: m.phase }
  )

  log(`${m.linearId} complete: ${result ? result.slice(0, 120) : 'done'}`)
}
