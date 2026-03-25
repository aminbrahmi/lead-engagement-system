import os
import sys
import json
import time
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from crewai import Crew, Process, Task
from tests.mock_agents import create_mock_collector, create_mock_writer

# ─────────────────────────────────────────────
# TEST 1 : est-ce que les agents se créent bien ?
# ─────────────────────────────────────────────
def test_agents_creation():
    print("\n[TEST 1] Création des agents...")
    try:
        collector = create_mock_collector()
        writer    = create_mock_writer()
        assert collector is not None
        assert writer is not None
        print("  OK — Les 2 agents sont créés")
        return collector, writer
    except Exception as e:
        print(f"  ERREUR — {e}")
        return None, None

# ─────────────────────────────────────────────
# TEST 2 : est-ce que les tâches se définissent bien ?
# ─────────────────────────────────────────────
def test_tasks_creation(collector, writer):
    print("\n[TEST 2] Création des tâches...")
    try:
        task1 = Task(
            description="Donne un profil fictif simple d'un lead B2B en JSON avec: nom, poste, score (0-100), segment.",
            expected_output="Un JSON avec nom, poste, score, segment",
            agent=collector
        )
        task2 = Task(
            description="Rédige un email court de prospection (3 lignes) basé sur le profil du lead.",
            expected_output="Un email avec objet et corps",
            agent=writer,
            context=[task1]
        )
        assert task1 is not None
        assert task2 is not None
        print("  OK — Les 2 tâches sont créées")
        return task1, task2
    except Exception as e:
        print(f"  ERREUR — {e}")
        return None, None

# ─────────────────────────────────────────────
# TEST 3 : est-ce que le Crew s'assemble bien ?
# ─────────────────────────────────────────────
def test_crew_assembly(collector, writer, task1, task2):
    print("\n[TEST 3] Assemblage du Crew...")
    try:
        crew = Crew(
            agents=[collector, writer],
            tasks=[task1, task2],
            process=Process.sequential,
            verbose=True
        )
        assert crew is not None
        print("  OK — Crew assemblé avec succès")
        return crew
    except Exception as e:
        print(f"  ERREUR — {e}")
        return None

# ─────────────────────────────────────────────
# TEST 4 : est-ce que le pipeline s'exécute de bout en bout ?
# ─────────────────────────────────────────────
def test_crew_execution(crew):
    print("\n[TEST 4] Exécution du pipeline complet...")
    try:
        start = time.time()
        result = crew.kickoff()
        duration = round(time.time() - start, 2)

        assert result is not None
        assert len(str(result)) > 10   # résultat non vide

        print(f"  OK — Pipeline exécuté en {duration}s")
        print(f"  Résultat :\n{'-'*40}\n{result}\n{'-'*40}")
        return result
    except Exception as e:
        print(f"  ERREUR — {e}")
        return None

# ─────────────────────────────────────────────
# RUNNER — lance tous les tests dans l'ordre
# ─────────────────────────────────────────────
def run_all_tests():
    print("=" * 50)
    print("  TESTS ORCHESTRATION — LEAD ENGAGEMENT SYSTEM")
    print("=" * 50)

    results = {"passed": 0, "failed": 0}

    # Test 1
    collector, writer = test_agents_creation()
    if collector: results["passed"] += 1
    else: results["failed"] += 1; return results

    # Test 2
    task1, task2 = test_tasks_creation(collector, writer)
    if task1: results["passed"] += 1
    else: results["failed"] += 1; return results

    # Test 3
    crew = test_crew_assembly(collector, writer, task1, task2)
    if crew: results["passed"] += 1
    else: results["failed"] += 1; return results

    # Test 4
    result = test_crew_execution(crew)
    if result: results["passed"] += 1
    else: results["failed"] += 1

    # Résumé
    print("\n" + "=" * 50)
    print(f"  RÉSULTAT : {results['passed']}/4 tests passés")
    if results["failed"] == 0:
        print("  Orchestrateur prêt pour les vrais agents !")
    else:
        print("  Corrige les erreurs avant de continuer.")
    print("=" * 50)

    return results

if __name__ == "__main__":
    run_all_tests()