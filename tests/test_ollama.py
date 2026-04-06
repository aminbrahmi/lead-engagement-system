"""
test_ollama.py — check which models are available and working in your Ollama instance.

Run: python test_ollama.py
"""

import json
import requests
from ollama import chat, list as ollama_list

OLLAMA_BASE = "http://localhost:11434"

# Models we want to use in the pipeline
WANTED_MODELS = [
    "gpt-oss",
    "gpt-oss:20b",
    "gpt-oss:120b",
    "gemini-3-flash-preview",
    "llama3.2",
    "llama3.1:8b",
    "llama3.3:70b",
    "mistral",
    "qwen2.5:7b",
    "deepseek-r1:7b",
]

TEST_PROMPT = "Reply with exactly one sentence: what is the capital of France?"


def check_ollama_running() -> bool:
    try:
        r = requests.get(f"{OLLAMA_BASE}/api/tags", timeout=5)
        return r.status_code == 200
    except Exception:
        return False


def get_installed_models() -> list[str]:
    try:
        result = ollama_list()
        return [m.model for m in result.models]
    except Exception as e:
        print(f"  ❌ Could not list models: {e}")
        return []


def test_model(model_name: str) -> dict:
    try:
        response = chat(
            model=model_name,
            messages=[{"role": "user", "content": TEST_PROMPT}],
        )
        reply = response.message.content.strip()[:120]
        return {"status": "✅ OK", "reply": reply}
    except Exception as e:
        err = str(e)
        if "404" in err or "not found" in err.lower():
            return {"status": "❌ not found", "reply": ""}
        return {"status": f"⚠️  error: {err[:80]}", "reply": ""}


def main():
    print("=" * 60)
    print("  Ollama model tester")
    print("=" * 60)

    # 1 — is Ollama running?
    print("\n[1] Checking Ollama is running...")
    if not check_ollama_running():
        print("  ❌ Ollama is NOT running.")
        print("  → Start it with:  ollama serve")
        return
    print(f"  ✅ Ollama is running at {OLLAMA_BASE}")

    # 2 — list installed models
    print("\n[2] Installed models:")
    installed = get_installed_models()
    if not installed:
        print("  (none — run: ollama pull <model_name>)")
    for m in installed:
        print(f"  • {m}")

    # 3 — test each wanted model
    print("\n[3] Testing pipeline models:")
    print(f"  {'Model':<35} {'Status':<25} {'Reply preview'}")
    print("  " + "-" * 90)

    working = []
    for model in WANTED_MODELS:
        result = test_model(model)
        status = result["status"]
        reply  = result["reply"]
        print(f"  {model:<35} {status:<25} {reply}")
        if "✅" in status:
            working.append(model)

    # 4 — also test every installed model that wasn't in our list
    extra = [m for m in installed if m not in WANTED_MODELS]
    if extra:
        print("\n[4] Other installed models (not in wanted list):")
        print(f"  {'Model':<35} {'Status':<25} {'Reply preview'}")
        print("  " + "-" * 90)
        for model in extra:
            result = test_model(model)
            print(f"  {model:<35} {result['status']:<25} {result['reply']}")
            if "✅" in result["status"]:
                working.append(model)

    # 5 — recommendation
    print("\n[5] Summary")
    print("=" * 60)
    if working:
        best = working[0]
        print(f"  Working models: {working}")
        print(f"\n  ✅ Recommended — add to your .env:")
        print(f"\n     PARSER_MODEL={best}")
        print(f"     ENRICHER_MODEL={best}")
        print(f"     QUALIFIER_MODEL=ollama/{best}")
    else:
        print("  ⚠️  No working Ollama models found.")
        print("  → Pull a model with one of these commands:")
        print("     ollama pull llama3.2        (~2 GB, fast)")
        print("     ollama pull llama3.1:8b     (~4.7 GB, better)")
        print("     ollama pull qwen2.5:7b      (~4.4 GB, great for JSON)")
        print("     ollama pull gpt-oss         (if available in your Ollama version)")
    print()


if __name__ == "__main__":
    main()