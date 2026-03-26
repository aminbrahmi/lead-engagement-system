# test_tavily.py
import os
import requests
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("TAVILY_API_KEY")
print(f"Tavily API Key: {api_key[:10]}...{api_key[-5:] if api_key else 'MISSING'}")

if api_key:
    try:
        resp = requests.post(
            "https://api.tavily.com/search",
            json={
                "api_key": api_key,
                "query": "Berlin AI startup funding 2024",
                "max_results": 5
            },
            timeout=10
        )
        print(f"Status: {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            print(f"Found {len(data.get('results', []))} results")
        else:
            print(f"Error: {resp.text}")
    except Exception as e:
        print(f"Error: {e}")