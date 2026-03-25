import os
from crewai import Agent
from tools.contact_finder import ContactFinderTool
from tools.name_enricher import NameEnricherTool

def create_qualifier_agent():
    return Agent(
        role="B2B Lead Qualifier",
        goal=(
            "For unknown leads, find their real name using NameEnricherTool. "
            "Then find email AND phone using ContactFinderTool cascade. "
            "Score and classify each lead as hot/warm/cold."
        ),
        backstory=(
            "You are a senior B2B sales strategist with 10 years experience. "
            "You always find the real person behind each company. "
            "You use every available tool to find contact information."
        ),
        tools=[NameEnricherTool(), ContactFinderTool()],
        llm=os.getenv("QUALIFIER_MODEL", "groq/openai/gpt-oss-120b"),
        verbose=True,
        max_iter=15
    )