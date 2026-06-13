# SolarMind — Claude Code instructions

## Project
LangGraph text-to-SQL agent + Streamlit UI over Plant A solar monitoring data (9.4 years,
DuckDB backend). Track: Enerparc open track, Energy/AI Hackathon Munich.

## Linear sync (required)
Issues live in Linear project **"Enerparc Open Track (Plant A)"**, team **AI Kanban Pilot**.
Milestones: AI-75 (M0) through AI-83 (M8).

**After completing each milestone, you MUST update its Linear issue status:**
- Starting a milestone → set state to **In Progress**
- Milestone done → set state to **Done**

Use the Linear MCP tools (`mcp__claude_ai_Linear__save_issue`) with the issue ID (e.g. `AI-76`)
and the `state` field. Do not skip this step — it is the only way the team can follow progress.

## Stack
- Python + DuckDB (embedded, no server)
- LangGraph agent, `langchain-groq`, model `llama-3.3-70b-versatile`
- `GROQ_API_KEY` in `.env` (gitignored)
- Streamlit UI
- `pvlib` for solar physics (imported, usage decided per milestone)

## Data
Raw parquet lives outside the repo at `D:\EnergyHack\database\Plant A (start here)`.
Each dev runs `python db/loader.py` to build their own `solar.duckdb` (gitignored).
See `db/` for schema and loader details.

## Key data gotchas
- Inverter IDs follow `NN.GG.UUU` (plant.group.unit) — parse into separate columns
- DV/EVU intervals = curtailment — exclude from fault/loss calculations, show separately
- Year 1 is NOT fully healthy — filter commissioning ramp-up and outages before baselining
- Minute-interval data → use 1/60 h for energy accumulation

## Commit style
Short imperative subject line. No body unless the why is non-obvious.
