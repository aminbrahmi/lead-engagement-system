# agents/researcher.py
# Agent 3.5 — Lead Researcher
# Before Agent 3 writes emails, this agent gathers
# personal details about each qualified lead :
# recent posts, interviews, LinkedIn activity,
# company news, product launches, personal interests

import os
from crewai import Agent
from tools.search_tool import TavilySearchTool

def create_researcher_agent():
    return Agent(
        role="Lead Intelligence Researcher",
        goal=(
            "For each qualified lead, gather specific personal and professional details "
            "that will make a cold email feel warm and relevant. "
            "Find recent interviews, LinkedIn posts, company news, product launches, "
            "or any public statement the person made. "
            "The more specific and recent, the better."
        ),
        backstory=(
            "You are an expert sales intelligence researcher. "
            "You know that a cold email referencing a specific podcast interview, "
            "a LinkedIn post, or a recent product launch gets 10x more replies "
            "than a generic one. You dig deep to find these hooks."
        ),
        tools=[TavilySearchTool()],
        llm=os.getenv("COLLECTOR_MODEL", "groq/openai/gpt-oss-20b"),
        verbose=True,
        max_iter=10
    )