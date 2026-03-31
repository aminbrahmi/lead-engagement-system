# tests/test_ftl_api.py
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter
import requests, os
from dotenv import load_dotenv
load_dotenv()
token = os.getenv("FTL_TOKEN")

session = requests.Session()

retries = Retry(
    total=3,
    backoff_factor=1
)

session.mount("https://", HTTPAdapter(max_retries=retries))

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
    timeout=30
)

print(f"Status  : {resp.status_code}")
print(f"Response: {resp.json()}")