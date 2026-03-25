import os
from crewai import Agent
from tools.search_tool import TavilySearchTool
from tools.scraper_tool import CrawleeTool

MODELS = [
    ("primary",   "groq/openai/gpt-oss-20b"),
    ("fallback1", "gemini/gemini-2.5-flash"),
    ("fallback2", "groq/openai/gpt-oss-120b"),
    ("fallback3", "groq/llama-3.3-70b-versatile"),
]

def create_collector_agent(model_tier: str = "primary"):
    model = next(
        (m for tier, m in MODELS if tier == model_tier),
        MODELS[0][1]
    )
    print(f"[Agent] Model: {model} ({model_tier})")
    return Agent(
        role="B2B Lead Collector",
        goal=(
            "Find 5+ unique leads from different companies using web search. "
            "Run multiple searches. Never repeat the same company twice. "
            "Return real names with source URLs."
        ),
        backstory=(
            "You are an expert B2B data sourcing specialist. "
            "You find real decision-makers on the web."
        ),
        tools=[TavilySearchTool(), CrawleeTool()],
        llm=model,
        verbose=True,
        max_iter=8
    )