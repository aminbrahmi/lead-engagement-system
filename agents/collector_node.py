# agents/collector_node.py
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage  # ← added AIMessage
from langgraph.prebuilt import create_react_agent

from tools.search_tool import TavilySearchTool
from agents.llm_factory import get_collector_llm
from orchestration.prompts import COLLECTOR_SYSTEM, collector_user_prompt


def _extract_text(message) -> str:
    """Handles both plain string and list-of-blocks content (Anthropic/Claude models)."""
    content = message.content
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            block["text"] for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        )
    return str(content)


def run_collector(campaign_prompt: str, criteria: dict) -> str:
    llm   = get_collector_llm()
    tools = [TavilySearchTool()]
    agent = create_react_agent(model=llm, tools=tools)

    result = agent.invoke({
        "messages": [
            SystemMessage(content=COLLECTOR_SYSTEM),
            HumanMessage(content=collector_user_prompt(campaign_prompt, criteria)),
        ]
    })

    # Walk from the end — find last AIMessage with real text
    for msg in reversed(result["messages"]):
        if isinstance(msg, AIMessage):
            text = _extract_text(msg)
            if text.strip():
                return text
    return ""