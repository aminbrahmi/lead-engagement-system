from crewai import Agent
import os

def create_mock_collector():
    return Agent(
        role="Collecteur de leads",
        goal="Collecter et qualifier les informations d'un lead",
        backstory="Tu es un expert en recherche d'informations B2B.",
        llm="groq/llama-3.1-8b-instant",  # format natif CrewAI
        verbose=True
    )

def create_mock_writer():
    return Agent(
        role="Rédacteur d'emails",
        goal="Rédiger des emails de prospection personnalisés",
        backstory="Tu es un expert en copywriting B2B.",
        llm="groq/llama-3.1-8b-instant",
        verbose=True
    )