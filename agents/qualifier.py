# agents/qualifier.py
import os
from crewai import Agent
from tools.email_finder import EmailFinderTool
from tools.name_enricher import NameEnricherTool

def create_qualifier_agent():
    return Agent(
        role="B2B Lead Qualifier",
        goal=(
            "For each lead with unknown name, find the real name first using NameEnricherTool. "
            "Then score each lead from 0 to 100. "
            "Then find emails using EmailFinderTool. "
            "Filter irrelevant profiles."
        ),
        backstory=(
            "You are a senior B2B sales strategist with 10 years of experience. "
            "You never give up on a lead just because the name is missing. "
            "You always search for the real person before evaluating the lead."
        ),
        tools=[NameEnricherTool(), EmailFinderTool()],
        llm=os.getenv("QUALIFIER_MODEL", "groq/openai/gpt-oss-20b"),
        verbose=True,
        max_iter=15
    )