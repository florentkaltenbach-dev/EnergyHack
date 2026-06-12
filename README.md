# ☀️ SolarMind
### Solar Plant AI Chatbot — Enerparc Track · Energy/AI Hackathon Munich

---

## Quick start (do this once per machine)

```bash
# 1. Clone the repo
git clone https://github.com/YOUR_USERNAME/solar-mind.git
cd solar-mind

# 2. Install dependencies
pip install duckdb pandas pyarrow openpyxl pvlib plotly streamlit \
            langgraph langchain langchain-anthropic python-dotenv

# 3. Add your API key
echo "ANTHROPIC_API_KEY=sk-ant-..." > .env

# 4. Copy all data files into data/  (get them from the Enerparc dataset)

# 5. Load data into the database (P1 does this)
python db/loader.py

# 6. Verify everything works
python test_setup.py

# 7. Launch the app
streamlit run app/app.py
```

---

## Project structure

```
solar_agent/
├── .env                    ← API key (never commit!)
├── solar.duckdb            ← Database (never commit — too large)
├── test_setup.py           ← Run this to verify everything works
│
├── data/
│   ├── main_monitoring_data.parquet
│   ├── errorcodes.parquet
│   ├── Additional_Data/
│   │   ├── feed-in-tarrifs.xlsx
│   │   ├── System_Overview.xlsx
│   │   └── Tickets.xlsx
│   └── Errorcodes/
│       └── errorcodes_description.xlsx
│
├── db/
│   ├── loader.py           ← P1: loads raw files → solar.duckdb
│   └── db.py               ← P1: run_query(), get_schema() helpers
│
├── agent/
│   ├── tools.py            ← P2: LangChain tools (SQL, charts)
│   ├── prompts.py          ← P2 + P3: system prompt + fault rules
│   └── agent.py            ← P2: invoke_agent() — P4 imports this
│
└── app/
    └── app.py              ← P4: Streamlit chat UI
```

---

## Team roles

| Person | Role | Owns |
|--------|------|------|
| P1 | Data Engineer | `db/loader.py`, `db/db.py` |
| P2 | Agent Engineer | `agent/tools.py`, `agent/agent.py`, `agent/prompts.py` |
| P3 | Solar Analyst | Fills fault rules in `agent/prompts.py`, writes demo questions |
| P4 | UI & Demo | `app/app.py`, rehearses pitch |

## Critical handoffs

| When | From → To | What |
|------|-----------|------|
| Hour 2 | P1 → All | `schema.txt` — column names |
| Hour 5 | P1 → P2 | `solar.duckdb` + `db/db.py` ready |
| Hour 9 | P3 → P2 | Fault rules + 15 demo questions |
| Hour 16 | P2 → P4 | `invoke_agent()` working, integration sync |
