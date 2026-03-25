# tests/test_ftl_api.py
import requests, os
from dotenv import load_dotenv
load_dotenv()

token = os.getenv("FTL_TOKEN")

resp = requests.post(
    "https://app-back-qa.findthatlead.com/search/lead",
    headers={
        "Authorization": f"Bearer {token}",
        "Content-Type":  "application/json",
        "Origin":        "https://dashboard.findthatlead.com",
        "Referer":       "https://dashboard.findthatlead.com/"
    },
    json={
        "get_linkedin_url": True,
        "name":    "Florian",
        "surname": "Wenzel",
        "domain":  "mirelo.ai",
        "enrich":  True
    },
    timeout=10
)

print(f"Status  : {resp.status_code}")
print(f"Response: {resp.json()}")