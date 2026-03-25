# Ce script teste si chaque modèle peut :
# 1. Appeler un outil externe (TavilySearchTool) sans erreur
# 2. Retourner des leads structurés en JSON
# 3. Le faire dans un temps acceptable
# On compare 3 modèles : GPT-OSS 120B (Groq), GPT-OSS 20B (Groq), Nemotron 3 Nano (OpenRouter)

import os
import time
from dotenv import load_dotenv
load_dotenv()

from crewai import Agent, Task, Crew, Process
from tools.search_tool import TavilySearchTool

# Liste des modèles à tester
# Chaque entrée : (nom lisible, identifiant LiteLLM, clé API env var, base URL si nécessaire)
MODELS = [
    {
        "name": "GPT-OSS 120B (Groq)",
        "model_id": "groq/openai/gpt-oss-120b",
        "api_key_env": "GROQ_API_KEY",
        "base_url": None   # Groq est supporté nativement par LiteLLM
    },
    {
        "name": "GPT-OSS 20B (Groq)",
        "model_id": "groq/openai/gpt-oss-20b",
        "api_key_env": "GROQ_API_KEY",
        "base_url": None
    },
    {
        "name": "Nemotron 3 Nano (OpenRouter)",
        "model_id": "openrouter/nvidia/llama-3.1-nemotron-nano-8b-v1",
        "api_key_env": "OPENROUTER_API_KEY",
        "base_url": "https://openrouter.ai/api/v1"
    },
]

# La tâche qu'on demande à chaque agent :
# chercher des leads réels via Tavily et les retourner en JSON
TASK_DESCRIPTION = """
Use TavilySearchTool to search: "CEO healthtech startup Tunisia 2024"
Then search again with: "Tunisian health startup founder CEO name LinkedIn"
Return a JSON array of 3+ leads with exactly these fields:
[{"name": "...", "company": "...", "role": "...", "location": "..."}]
"""

results = []

for config in MODELS:
    print(f"\n{'='*55}")
    print(f"Testing : {config['name']}")
    print(f"Model ID: {config['model_id']}")
    print('='*55)

    start = time.time()
    try:
        # Crée un agent CrewAI avec ce modèle
        # L'agent a accès à TavilySearchTool pour chercher sur le web
        agent = Agent(
            role="B2B Lead Collector",
            goal="Find real leads using web search tools",
            backstory="You are a B2B data sourcing expert.",
            tools=[TavilySearchTool()],
            llm=config["model_id"],
            verbose=False,
            max_iter=6
        )

        # La tâche décrit exactement ce que l'agent doit faire
        task = Task(
            description=TASK_DESCRIPTION,
            expected_output="JSON array of 3+ leads",
            agent=agent
        )

        # Le Crew orchestre l'exécution séquentielle
        crew = Crew(
            agents=[agent],
            tasks=[task],
            process=Process.sequential,
            verbose=False
        )

        # Lance l'exécution et mesure le temps
        result = crew.kickoff()
        elapsed = round(time.time() - start, 2)
        result_str = str(result)

        # Compte le nombre de leads retournés
        # en cherchant combien de fois "name" apparaît dans le JSON
        lead_count = result_str.count('"name"')

        # Vérifie si le résultat est un JSON valide
        has_json = "[" in result_str and "]" in result_str

        print(f"  Status    : SUCCESS ✓")
        print(f"  Time      : {elapsed}s")
        print(f"  Leads     : {lead_count}")
        print(f"  Valid JSON : {has_json}")
        print(f"  Preview   : {result_str[:250]}")

        results.append({
            "name": config["name"],
            "status": "SUCCESS",
            "time": elapsed,
            "leads": lead_count,
            "valid_json": has_json
        })

    except Exception as e:
        elapsed = round(time.time() - start, 2)
        error_msg = str(e)[:150]
        print(f"  Status : FAILED ✗")
        print(f"  Time   : {elapsed}s")
        print(f"  Error  : {error_msg}")

        results.append({
            "name": config["name"],
            "status": "FAILED",
            "time": elapsed,
            "leads": 0,
            "error": error_msg
        })

    # Pause entre chaque modèle pour éviter les rate limits
    time.sleep(4)

# Affiche le tableau comparatif final
print(f"\n\n{'='*55}")
print("  FINAL COMPARISON")
print('='*55)
print(f"{'Model':<35} {'Status':<10} {'Time':>7} {'Leads':>7}")
print("-"*55)

for r in results:
    status = r["status"]
    time_s = f"{r['time']}s"
    leads  = str(r["leads"])
    print(f"{r['name']:<35} {status:<10} {time_s:>7} {leads:>7}")

# Recommandation automatique
successful = [r for r in results if r["status"] == "SUCCESS"]
if successful:
    best = max(successful, key=lambda x: (x["leads"], -x["time"]))
    print(f"\n  Best model : {best['name']}")
    print(f"  Reason     : {best['leads']} leads in {best['time']}s")