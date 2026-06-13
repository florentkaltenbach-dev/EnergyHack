"""
Run this to verify the whole stack is working before the demo.
Usage: python test_setup.py
"""

import sys
import os
import traceback

# Windows consoles default to cp1252 and choke on the ✅/── chars below.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

PASS = "✅"
FAIL = "❌"
WARN = "⚠️ "

errors = []

# ── 1. Environment ─────────────────────────────────────────────────────────────
print("\n── 1. Environment ──────────────────────────────")
try:
    from dotenv import load_dotenv
    load_dotenv()
    api_key = os.getenv("GROQ_API_KEY", "")
    if api_key:
        print(f"{PASS} GROQ_API_KEY found  (ends with …{api_key[-4:]})")
    else:
        print(f"{FAIL} GROQ_API_KEY not set in .env")
        errors.append("Missing API key")
except Exception as e:
    print(f"{FAIL} dotenv import failed: {e}")
    errors.append(str(e))

# ── 2. Imports ─────────────────────────────────────────────────────────────────
print("\n── 2. Package imports ──────────────────────────")
packages = [
    ("duckdb",            "duckdb"),
    ("pandas",            "pandas"),
    ("plotly",            "plotly"),
    ("langchain_groq",       "langchain_groq"),
    ("langgraph",         "langgraph"),
    ("streamlit",         "streamlit"),
]
for label, mod in packages:
    try:
        __import__(mod)
        print(f"{PASS} {label}")
    except ImportError as e:
        print(f"{FAIL} {label}  →  {e}")
        errors.append(f"Missing package: {label}")

# ── 3. Database ────────────────────────────────────────────────────────────────
print("\n── 3. Database ─────────────────────────────────")
db_path = os.path.join(ROOT, "solar.duckdb")
if not os.path.exists(db_path):
    print(f"{WARN} solar.duckdb not found — run:  python db/loader.py")
else:
    try:
        from db.db import get_schema, run_query
        schema = get_schema()
        print(f"{PASS} Connected to solar.duckdb")
        tables = [line.split()[1] for line in schema.splitlines() if line.startswith("TABLE")]
        print(f"{PASS} Tables found: {', '.join(tables)}")

        # Quick sanity query
        df = run_query("SELECT COUNT(*) AS n FROM fact_power")
        print(f"{PASS} fact_power rows: {df['n'].iloc[0]:,}")
    except Exception as e:
        print(f"{FAIL} DB error: {e}")
        errors.append(str(e))

# ── 4. Agent (lightweight — just check it builds) ─────────────────────────────
print("\n── 4. Agent build ──────────────────────────────")
try:
    from agent.agent import _agent, _llm, _tools
    print(f"{PASS} Agent constructed")
    print(f"{PASS} Tools: {[t.name for t in _tools]}")
except Exception as e:
    print(f"{FAIL} Agent failed to build: {e}")
    traceback.print_exc()
    errors.append(str(e))

# ── 5. Live API call (small) ───────────────────────────────────────────────────
print("\n── 5. Live API call ────────────────────────────")
if not os.getenv("GROQ_API_KEY"):
    print(f"{WARN} Skipping — no API key")
elif not os.path.exists(db_path):
    print(f"{WARN} Skipping — database not loaded yet")
else:
    try:
        from agent.agent import invoke_agent
        result = invoke_agent("How many tables are in the database? Give a one-sentence answer.")
        print(f"{PASS} Agent responded:")
        print(f"     {result['text'][:200]}")
    except Exception as e:
        print(f"{FAIL} Live call failed: {e}")
        traceback.print_exc()
        errors.append(str(e))

# ── Summary ────────────────────────────────────────────────────────────────────
print("\n── Summary ─────────────────────────────────────")
if errors:
    print(f"{FAIL} {len(errors)} issue(s) found:")
    for e in errors:
        print(f"   • {e}")
    sys.exit(1)
else:
    print(f"{PASS} All checks passed — ready for demo!")
    print("\n   Start the app:  streamlit run app/app.py\n")
