"""
P4 — UI & Demo
Streamlit chat interface.
Run: streamlit run app/app.py
"""

import sys
import os

# Make sure project root is on the path no matter where streamlit is launched from
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
from langchain_core.messages import HumanMessage, AIMessage

from agent.agent import invoke_agent

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="SolarMind",
    page_icon="☀️",
    layout="wide",
)

# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.image("https://img.icons8.com/emoji/96/sun-emoji.png", width=60)
    st.title("SolarMind")
    st.caption("AI assistant for solar plant operations")
    st.divider()
    st.markdown("**Example questions:**")
    examples = [
        "Which inverter had the most downtime in 2022?",
        "How much revenue did we lose from faults in summer 2021?",
        "Show a chart of monthly production for inverter 5 in 2020.",
        "Inverter 12 just triggered error 450 — what should I do?",
        "Which month had the highest feed-in tariff?",
        "Compare the worst 5 performing inverters last year.",
    ]
    for ex in examples:
        if st.button(ex, use_container_width=True, key=ex):
            st.session_state["prefill"] = ex

    st.divider()
    if st.button("🗑 Clear chat", use_container_width=True):
        st.session_state.messages = []
        st.session_state.lc_history = []
        st.rerun()

# ── Session state ──────────────────────────────────────────────────────────────
if "messages" not in st.session_state:
    st.session_state.messages = []          # [{role, content, chart?}]
if "lc_history" not in st.session_state:
    st.session_state.lc_history = []        # LangChain message objects for context

# ── Main area ──────────────────────────────────────────────────────────────────
st.title("☀️ SolarMind")
st.caption("Ask questions about your solar plant in plain English.")

# Render existing chat history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg.get("chart") is not None:
            st.plotly_chart(msg["chart"], use_container_width=True)

# Handle prefilled question from sidebar buttons
default_input = st.session_state.pop("prefill", "")

# Chat input
prompt = st.chat_input(
    "Ask about performance, faults, revenue…",
    key="chat_input",
) or default_input

if prompt:
    # Show user message immediately
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Get agent response
    with st.chat_message("assistant"):
        with st.spinner("Querying data…"):
            try:
                result = invoke_agent(prompt, chat_history=st.session_state.lc_history)
                answer = result["text"]
                chart  = result["chart"]

                st.markdown(answer)
                if chart is not None:
                    st.plotly_chart(chart, use_container_width=True)

                # Update LangChain history for multi-turn context
                st.session_state.lc_history.append(HumanMessage(content=prompt))
                st.session_state.lc_history.append(AIMessage(content=answer))
                # Keep last 10 turns to avoid huge prompts
                st.session_state.lc_history = st.session_state.lc_history[-20:]

                st.session_state.messages.append({
                    "role":    "assistant",
                    "content": answer,
                    "chart":   chart,
                })

            except Exception as e:
                err = f"⚠️ Error: {e}"
                st.error(err)
                st.session_state.messages.append({"role": "assistant", "content": err})
