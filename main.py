from dotenv import load_dotenv
load_dotenv()

from orchestration.crew import run_lead_pipeline

if __name__ == "__main__":
    campaign = input("Décris ta campagne : ")
    # Exemple : "Je veux contacter des CTOs dans des scale-ups parisiennes de plus de 50 employés qui ont récemment levé des fonds"

    result = run_lead_pipeline(campaign)

    print("\n===== LEADS COLLECTÉS =====")
    print(result)