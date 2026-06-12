"""
P2 — Agent Engineer
Main agent. P4 imports invoke_agent() from here.
"""

import os
from dotenv import load_dotenv
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage, ToolMessage
from langgraph.prebuilt import create_react_agent

import agent.tools as _tools_module
from agent.tools import get_database_schema, query_database, create_chart
from agent.prompts import SYSTEM_PROMPT

load_dotenv()

# ── Build the agent once at import time ───────────────────────────────────────
_llm = ChatAnthropic(
    model="claude-sonnet-4-5",
    api_key=os.getenv("ANTHROPIC_API_KEY"),
    max_tokens=4096,
)

_tools = [get_database_schema, query_database, create_chart]

_agent = create_react_agent(_llm, _tools)


# ── Helper: extract plain text from a LangChain message ──────────────────────
def _get_text(msg) -> str:
    content = getattr(msg, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        )
    return str(content)


# ── Public interface ───────────────────────────────────────────────────────────
def invoke_agent(question: str, chat_history: list | None = None) -> dict:
    """
    Ask the agent a question and get back a text answer + optional chart.

    Args:
        question:     Plain-English question from the user.
        chat_history: Optional list of previous LangChain message objects
                      (HumanMessage / AIMessage pairs).

    Returns:
        {
            "text":  str           — the agent's answer
            "chart": plotly Figure — or None if no chart was created
        }
    """
    # Reset chart state before this run
    _tools_module._last_chart = None

    # Build message list: system prompt + history + new question
    messages = [SystemMessage(content=SYSTEM_PROMPT)]
    if chat_history:
        messages.extend(chat_history)
    messages.append(HumanMessage(content=question))

    # Run the agent
    result = _agent.invoke({"messages": messages})

    # Extract the final AI text response (last AIMessage that has text)
    text = ""
    for msg in reversed(result["messages"]):
        if isinstance(msg, AIMessage):
            candidate = _get_text(msg)
            if candidate.strip():
                text = candidate
                break

    # Retrieve chart if one was created during this run
    chart = _tools_module._last_chart

    return {"text": text, "chart": chart}
