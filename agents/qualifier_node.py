# agents/qualifier_node.py
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage, ToolMessage
from langgraph.prebuilt import create_react_agent

from tools.email_finder import EmailFinderTool
from tools.name_enricher import NameEnricherTool
from agents.llm_factory import get_qualifier_llm
from orchestration.prompts import QUALIFIER_SYSTEM, qualifier_user_prompt


def _extract_text(message) -> str:
    content = message.content
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            block["text"] for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        )
    return str(content)


def run_qualifier(campaign_prompt: str, raw_leads_json: str) -> str:
    llm   = get_qualifier_llm()
    tools = [NameEnricherTool(), EmailFinderTool()]

    # ← increase recursion limit — 4 leads × (enrich + email + score) = many steps
    agent = create_react_agent(model=llm, tools=tools)

    result = agent.invoke(
        {
            "messages": [
                SystemMessage(content=QUALIFIER_SYSTEM),
                HumanMessage(content=qualifier_user_prompt(campaign_prompt, raw_leads_json)),
            ]
        },
        config={"recursion_limit": 80},   # ← was default 25, not enough
    )

    # Debug — print every message type and preview
    print(f"\n[DEBUG] Total messages: {len(result['messages'])}")
    for i, msg in enumerate(result["messages"]):
        msg_type = type(msg).__name__
        text     = _extract_text(msg)[:120].replace("\n", " ")
        print(f"  [{i}] {msg_type}: {text}")

    # Walk from end — first AIMessage with real text content
    for msg in reversed(result["messages"]):
        if isinstance(msg, AIMessage):
            text = _extract_text(msg)
            if text.strip():
                return text

    return ""