# tests/test_nvidia_models.py
# Ce script teste si chaque modèle NVIDIA gratuit sur OpenRouter
# peut appeler TavilySearchTool correctement via CrewAI
# et retourner des leads structurés en JSON

import os
import time
from dotenv import load_dotenv
load_dotenv()

from crewai import Agent, Task, Crew, Process
from tools.search_tool import TavilySearchTool

# Les 4 modèles NVIDIA gratuits trouvés sur OpenRouter
# On utilise le préfixe "openrouter/" pour que LiteLLM
# sache qu'il doit router vers OpenRouter
MODELS = [
    "openrouter/nvidia/nemotron-3-super-120b-a12b:free",
    "openrouter/nvidia/nemotron-3-nano-30b-a3b:free",
    "openrouter/nvidia/nemotron-nano-9b-v2:free",
    "openrouter/nvidia/nemotron-nano-12b-v2-vl:free",
]

# La tâche est identique pour tous les modèles
# pour que la comparaison soit équitable
TASK = """
Use TavilySearchTool to search: "CEO healthtech startup Tunisia 2024"
Then search again: "Tunisian health startup founder CEO name LinkedIn"
Return a JSON array of 3+ leads:
[{"name": "...", "company": "...", "role": "...", "location": "..."}]
"""

results = []

for model_id in MODELS:
    short_name = model_id.split("/")[-1]
    print(f"\n{'='*55}")
    print(f"Testing : {short_name}")
    print('='*55)

    start = time.time()
    try:
        # On crée un agent CrewAI avec ce modèle NVIDIA
        # L'agent a accès à TavilySearchTool pour faire
        # de vraies recherches web
        agent = Agent(
            role="B2B Lead Collector",
            goal="Find real leads using web search tools",
            backstory="You are a B2B data sourcing expert.",
            tools=[TavilySearchTool()],
            llm=model_id,
            verbose=False,
            max_iter=6
        )

        task = Task(
            description=TASK,
            expected_output="JSON array of 3+ leads",
            agent=agent
        )

        crew = Crew(
            agents=[agent],
            tasks=[task],
            process=Process.sequential,
            verbose=False
        )

        result = crew.kickoff()
        elapsed = round(time.time() - start, 2)
        result_str = str(result)

        # Compte le nombre de leads en cherchant
        # combien de fois "name" apparaît dans le JSON
        lead_count = result_str.count('"name"')
        has_json = "[" in result_str

        print(f"  Status    : SUCCESS ✓")
        print(f"  Time      : {elapsed}s")
        print(f"  Leads     : {lead_count}")
        print(f"  Preview   : {result_str[:200]}")

        results.append({
            "name": short_name,
            "status": "SUCCESS",
            "time": elapsed,
            "leads": lead_count,
        })

    except Exception as e:
        elapsed = round(time.time() - start, 2)
        # Extrait le message d'erreur principal
        # sans le stacktrace complet
        error_msg = str(e)[:120]
        print(f"  Status : FAILED ✗")
        print(f"  Time   : {elapsed}s")
        print(f"  Error  : {error_msg}")

        results.append({
            "name": short_name,
            "status": "FAILED",
            "time": elapsed,
            "leads": 0,
            "error": error_msg
        })

    # Pause de 5 secondes entre chaque modèle
    # pour éviter les rate limits OpenRouter
    time.sleep(5)

# Tableau comparatif final
print(f"\n\n{'='*60}")
print("  NVIDIA MODELS — FINAL COMPARISON")
print('='*60)
print(f"{'Model':<45} {'Status':<10} {'Time':>7} {'Leads':>6}")
print("-"*60)

for r in results:
    print(f"{r['name']:<45} {r['status']:<10} {r['time']:>6}s {r['leads']:>6}")

# Recommandation automatique basée sur
# nombre de leads trouvés et vitesse
successful = [r for r in results if r["status"] == "SUCCESS"]
if successful:
    best = max(successful, key=lambda x: (x["leads"], -x["time"]))
    print(f"\n  Best NVIDIA model : {best['name']}")
    print(f"  Reason            : {best['leads']} leads in {best['time']}s")
else:
    print("\n  No NVIDIA model passed tool calling test.")
    print("  Recommendation: use GPT-OSS 20B (Groq) when rate limit resets.")