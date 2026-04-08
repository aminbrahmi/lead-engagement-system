"""
benchmark.py — Test every model on every agent task, score results, pick winners.

Usage:
    python benchmark.py

Outputs a comparison table and writes results to data/benchmark_results.json
"""

import json
import os
import re
import time
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

from groq import Groq
try:
    import google.generativeai as genai
    HAS_GEMINI = bool(os.getenv("GOOGLE_API_KEY"))
except ImportError:
    HAS_GEMINI = False

# ── Models to test ────────────────────────────────────────────────────────────

MODELS = []

# Groq models
for m in ["openai/gpt-oss-120b", "llama-3.3-70b-versatile", "openai/gpt-oss-20b"]:
    MODELS.append({"provider": "groq", "model": m, "label": m.split("/")[-1]})

# Gemini
if HAS_GEMINI:
    MODELS.append({"provider": "gemini", "model": "gemini-2.5-flash", "label": "gemini-2.5-flash"})
else:
    print("[Benchmark] ⚠ GOOGLE_API_KEY not set — skipping Gemini models\n")

# ── LLM call wrapper ─────────────────────────────────────────────────────────

def call_llm(provider: str, model: str, system: str, user: str,
             max_tokens: int = 4096, temperature: float = 0) -> dict:
    """Returns {content, latency_s, tokens_out, error}."""
    start = time.time()
    try:
        if provider == "groq":
            client = Groq(api_key=os.getenv("GROQ_API_KEY"))
            resp = client.chat.completions.create(
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            )
            content = resp.choices[0].message.content or ""
            tokens  = resp.usage.completion_tokens if resp.usage else len(content) // 4
            return {"content": content, "latency_s": time.time() - start,
                    "tokens_out": tokens, "error": None}

        elif provider == "gemini":
            genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
            model_obj = genai.GenerativeModel(model)
            resp = model_obj.generate_content(
                f"{system}\n\n{user}",
                generation_config=genai.types.GenerationConfig(
                    temperature=temperature, max_output_tokens=max_tokens
                ),
            )
            content = resp.text or ""
            return {"content": content, "latency_s": time.time() - start,
                    "tokens_out": len(content) // 4, "error": None}

    except Exception as e:
        return {"content": "", "latency_s": time.time() - start,
                "tokens_out": 0, "error": str(e)}


# ── Test definitions ──────────────────────────────────────────────────────────
# Each test has: name, system prompt, user prompt, scoring function.
# Scoring function takes (content: str) -> dict with scores 0-100 per criterion.

CAMPAIGN = "Reach out to CTOs of AI startups in Berlin that raised funding in the last 6 months"

# ---- Test 1: PARSER ----

def score_parser(content: str) -> dict:
    scores = {}
    # Valid JSON?
    content = re.sub(r'```json|```', '', content).strip()
    match = re.search(r'\{.*\}', content, re.DOTALL)
    if not match:
        return {"valid_json": 0, "has_fields": 0, "query_quality": 0}
    try:
        data = json.loads(match.group(0))
    except Exception:
        return {"valid_json": 0, "has_fields": 0, "query_quality": 0}

    scores["valid_json"] = 100

    # Has required fields?
    required = ["job_titles", "location", "industry", "search_queries"]
    present  = sum(1 for f in required if data.get(f))
    scores["has_fields"] = int(present / len(required) * 100)

    # Query quality
    queries = data.get("search_queries", [])
    good = [q for q in queries if 3 < len(q.split()) <= 10]
    scores["query_quality"] = int(len(good) / max(len(queries), 1) * 100) if queries else 0

    return scores


PARSER_TEST = {
    "name": "Parser",
    "system": "Extract structured info from a campaign brief. Return ONLY valid JSON.",
    "user": f"""Extract structured information from this sales campaign brief.

Campaign brief: "{CAMPAIGN}"

Return ONLY valid JSON (no markdown fences):
{{"job_titles": ["exact title"], "location": "location", "industry": "industry", "company_type": "startup|enterprise", "search_queries": ["query1", "query2", "query3", "query4", "query5"]}}""",
    "score_fn": score_parser,
    "max_tokens": 1024,
}


# ---- Test 2: COLLECTOR (extraction) ----

SAMPLE_SEARCH_BLOB = """
### Search: Berlin AI startup CTO funding 2024
- [Tower raises €5.5M for AI data engineering](https://eu-startups.com/tower-raises)
  Berlin-based Tower, founded by Brad Heller (CTO), raised €5.5M seed round in March 2024.
- [Parloa triples valuation to $3B](https://siliconrepublic.com/parloa)
  Berlin AI startup Parloa raised $350M Series D led by Altimeter. CTO is Malte Kosub.
- [GeneralMind raises $12M for AI autopilot](https://trendingtopics.eu/generalmind)
  Berlin startup GeneralMind raised $12M seed. CEO Lennart von Hardenberg.
- [Bounti raises €4M for AI frontline workers](https://techfundingnews.com/bounti)
  Berlin-based Bounti raised €4M seed in May 2024 for AI platform.
- [Mirelo secures $41M seed for AI video](https://musicbusinessworldwide.com/mirelo)
  Berlin startup Mirelo raised $41M seed. Founded by Florian Wenzel.
"""

def score_collector(content: str) -> dict:
    content = re.sub(r'```json|```', '', content).strip()
    match = re.search(r'\[.*\]', content, re.DOTALL)
    if not match:
        # Try truncation recovery
        if content.startswith('['):
            last = content.rfind('}')
            if last > 0:
                try:
                    data = json.loads(content[:last+1] + ']')
                except Exception:
                    return {"valid_json": 0, "lead_count": 0, "unique_companies": 0,
                            "unique_names": 0, "has_urls": 0}
            else:
                return {"valid_json": 0, "lead_count": 0, "unique_companies": 0,
                        "unique_names": 0, "has_urls": 0}
        else:
            return {"valid_json": 0, "lead_count": 0, "unique_companies": 0,
                    "unique_names": 0, "has_urls": 0}
    else:
        try:
            data = json.loads(match.group(0))
        except Exception:
            return {"valid_json": 0, "lead_count": 0, "unique_companies": 0,
                    "unique_names": 0, "has_urls": 0}

    if not isinstance(data, list):
        return {"valid_json": 0, "lead_count": 0, "unique_companies": 0,
                "unique_names": 0, "has_urls": 0}

    scores = {"valid_json": 100}
    scores["lead_count"] = min(len(data) / 5 * 100, 100)

    companies = [l.get("company", "").lower() for l in data]
    scores["unique_companies"] = int(len(set(companies)) / max(len(companies), 1) * 100)

    names = [l.get("name", "unknown").lower() for l in data if l.get("name", "").lower() != "unknown"]
    scores["unique_names"] = int(len(set(names)) / max(len(names), 1) * 100) if names else 50

    urls = [l for l in data if l.get("source_url") and "example" not in l.get("source_url", "")]
    scores["has_urls"] = int(len(urls) / max(len(data), 1) * 100)

    return scores


COLLECTOR_TEST = {
    "name": "Collector",
    "system": "You are a B2B data sourcing specialist. Extract leads from search results.",
    "user": f"""Campaign: "{CAMPAIGN}"

Search results:
{SAMPLE_SEARCH_BLOB}

Extract 5+ UNIQUE leads. Each company and name must be DIFFERENT.
If you don't know a person's name, write "unknown".

Return ONLY a raw JSON array:
[{{"name":"First Last or unknown","company":"Company","role":"CTO","location":"Berlin","source_url":"article URL","notes":"funding info"}}]""",
    "score_fn": score_collector,
    "max_tokens": 4096,
}


# ---- Test 3: QUALIFIER (scoring) ----

SAMPLE_LEADS = json.dumps([
    {"name": "Brad Heller", "company": "Tower", "role": "CTO", "location": "Berlin",
     "email": "brad.heller@tower.ai", "email_source": "pattern", "notes": "Raised €5.5M seed 2024"},
    {"name": "Malte Kosub", "company": "Parloa", "role": "CTO", "location": "Berlin",
     "email": "malte@parloa.com", "email_source": "google", "notes": "Raised $350M Series D"},
    {"name": "unknown", "company": "Bounti", "role": "CTO", "location": "Berlin",
     "email": None, "email_source": None, "notes": "Raised €4M seed"},
])

def score_qualifier(content: str) -> dict:
    content = re.sub(r'```json|```', '', content).strip()
    match = re.search(r'\[.*\]', content, re.DOTALL)
    if not match:
        return {"valid_json": 0, "all_leads_present": 0, "scores_vary": 0,
                "segments_correct": 0, "reason_quality": 0}
    try:
        data = json.loads(match.group(0))
    except Exception:
        return {"valid_json": 0, "all_leads_present": 0, "scores_vary": 0,
                "segments_correct": 0, "reason_quality": 0}

    scores = {"valid_json": 100}
    scores["all_leads_present"] = 100 if len(data) == 3 else int(len(data) / 3 * 100)

    # Scores should vary
    lead_scores = [l.get("score", 0) for l in data]
    scores["scores_vary"] = 100 if len(set(lead_scores)) > 1 else 0

    # Segment assignment
    correct = 0
    for l in data:
        seg   = l.get("segment", "")
        score = l.get("score", 0)
        email = l.get("email")
        if not email and seg == "cold":
            correct += 1
        elif email and score >= 45 and seg in ("warm", "hot"):
            correct += 1
        elif email and score < 45 and seg == "cold":
            correct += 1
    scores["segments_correct"] = int(correct / max(len(data), 1) * 100)

    # Reason quality
    reasons = [l.get("reason", "") for l in data]
    good_reasons = [r for r in reasons if len(r) > 20]
    scores["reason_quality"] = int(len(good_reasons) / max(len(reasons), 1) * 100)

    return scores


QUALIFIER_TEST = {
    "name": "Qualifier",
    "system": "You are a B2B sales strategist. Score leads rigorously.",
    "user": f"""Campaign: "{CAMPAIGN}"

Leads:
{SAMPLE_LEADS}

Score each 0-99. Criteria: role(0-30), location(0-20), company fit(0-20), funding(0-20), data quality(0-10).
Unverified email → max 72. No email → max 40, cold. Scores must VARY.

Return ONLY JSON array:
[{{"name":"...","company":"...","score":N,"segment":"hot|warm|cold","reason":"short explanation","keep":true/false}}]""",
    "score_fn": score_qualifier,
    "max_tokens": 4096,
}


# ---- Test 4: ENRICHER (distillation) ----

SAMPLE_RESEARCH = """
### Tower raised funding 2024 OR 2025 startup
ANSWER: Tower, a Berlin-based AI data engineering startup, raised €5.5M in seed funding in March 2024.
- [Tower Raises €5.5M](https://eu-startups.com/tower): Brad Heller, CTO, said "We're building the last mile for data engineers."

### "Brad Heller" Tower CTO
- [LinkedIn](https://linkedin.com/in/bradheller): Brad Heller, CTO at Tower. Previously at Databricks.

### Tower product AI platform technology
- [Tower Platform](https://tower.ai): Tower offers an AI-native data pipeline platform. Uses Python, dbt, Spark.
"""

def score_enricher(content: str) -> dict:
    content = re.sub(r'```json|```', '', content).strip()
    match = re.search(r'\{.*\}', content, re.DOTALL)
    if not match:
        return {"valid_json": 0, "fields_filled": 0, "no_hallucination": 0, "specificity": 0}
    try:
        data = json.loads(match.group(0))
    except Exception:
        return {"valid_json": 0, "fields_filled": 0, "no_hallucination": 0, "specificity": 0}

    scores = {"valid_json": 100}

    fields = ["recent_news", "person_highlights", "company_challenge", "tech_stack", "icebreaker", "value_angle"]
    empty_markers = {"no information found", "n/a", "not found", "none", ""}
    filled = sum(1 for f in fields if data.get(f, "").strip().lower() not in empty_markers and len(data.get(f, "")) > 15)
    scores["fields_filled"] = int(filled / len(fields) * 100)

    # Check for hallucination: invented funding amounts not in research
    all_text = json.dumps(data).lower()
    scores["no_hallucination"] = 100
    for fake in ["$100m", "$500m", "series b", "series c"]:
        if fake in all_text:
            scores["no_hallucination"] -= 30

    # Specificity: mentions real details (€5.5M, Brad Heller, Databricks, dbt)
    specifics = ["5.5m", "brad heller", "databricks", "dbt", "spark", "data engineer", "last mile"]
    found = sum(1 for s in specifics if s in all_text)
    scores["specificity"] = int(found / len(specifics) * 100)

    return scores


ENRICHER_TEST = {
    "name": "Enricher",
    "system": "You are a B2B sales research specialist. Extract facts only from the provided text. No invention.",
    "user": f"""Lead:
  Name: Brad Heller
  Company: Tower
  Role: CTO

Research:
{SAMPLE_RESEARCH}

Return ONLY raw JSON:
{{"recent_news":"...","person_highlights":"...","company_challenge":"...","tech_stack":"...","icebreaker":"...","value_angle":"..."}}""",
    "score_fn": score_enricher,
    "max_tokens": 2048,
}


# ---- Test 5: WRITER (email generation) ----

SAMPLE_INSIGHTS = {
    "recent_news": "Tower raised €5.5M seed funding in March 2024 for AI data engineering.",
    "person_highlights": "Brad Heller previously worked at Databricks, said 'We're building the last mile for data engineers.'",
    "company_challenge": "Bridging the gap between raw data and production-ready AI pipelines.",
    "tech_stack": "Python, dbt, Spark, Kubernetes",
    "icebreaker": "Tower's €5.5M seed round and Brad's Databricks background.",
    "value_angle": "Helping Tower scale their data pipeline automation.",
}

def score_writer(content: str) -> dict:
    content = re.sub(r'```json|```', '', content).strip()
    match = re.search(r'\{.*\}', content, re.DOTALL)
    if not match:
        return {"valid_json": 0, "has_subject": 0, "body_length": 0,
                "specificity": 0, "no_filler": 0}
    try:
        data = json.loads(match.group(0))
    except Exception:
        return {"valid_json": 0, "has_subject": 0, "body_length": 0,
                "specificity": 0, "no_filler": 0}

    scores = {"valid_json": 100}
    scores["has_subject"] = 100 if data.get("subject") and len(data["subject"]) > 5 else 0

    body = data.get("body", "")
    sentences = [s.strip() for s in re.split(r'[.!?]+', body) if s.strip()]
    scores["body_length"] = 100 if 3 <= len(sentences) <= 7 else max(0, 100 - abs(len(sentences) - 5) * 15)

    # Specificity: references real details
    body_lower = body.lower()
    specifics = ["5.5m", "tower", "databricks", "data engineer", "last mile", "brad"]
    found = sum(1 for s in specifics if s in body_lower)
    scores["specificity"] = int(found / len(specifics) * 100)

    # No filler phrases
    filler = ["i came across", "hope this finds you", "i hope", "reaching out because",
              "i wanted to", "just wanted to", "i noticed that"]
    filler_found = sum(1 for f in filler if f in body_lower)
    scores["no_filler"] = max(0, 100 - filler_found * 30)

    return scores


WRITER_TEST = {
    "name": "Writer",
    "system": "You are an expert B2B cold email copywriter. Short, specific, no filler.",
    "user": f"""Campaign: {CAMPAIGN}

Lead: Brad Heller, CTO @ Tower (brad.heller@tower.ai)

Insights:
{json.dumps(SAMPLE_INSIGHTS, indent=2)}

Write a cold email. 4-6 sentences, specific opener, soft CTA.
Return ONLY JSON: {{"subject":"...","body":"..."}}""",
    "score_fn": score_writer,
    "max_tokens": 2048,
}


# ── All tests ─────────────────────────────────────────────────────────────────

ALL_TESTS = [PARSER_TEST, COLLECTOR_TEST, QUALIFIER_TEST, ENRICHER_TEST, WRITER_TEST]


# ── Runner ────────────────────────────────────────────────────────────────────

def run_benchmark():
    results = []
    print("=" * 90)
    print(f"  MODEL BENCHMARK — {len(MODELS)} models × {len(ALL_TESTS)} agents = {len(MODELS)*len(ALL_TESTS)} tests")
    print("=" * 90)
    print()

    for test in ALL_TESTS:
        print(f"━━━ Agent: {test['name']} ━━━")
        for model_info in MODELS:
            label = model_info["label"]
            print(f"  Testing {label}...", end=" ", flush=True)

            # Add delay between Groq calls to respect TPM
            if model_info["provider"] == "groq":
                time.sleep(2)

            resp = call_llm(
                model_info["provider"], model_info["model"],
                test["system"], test["user"],
                max_tokens=test.get("max_tokens", 4096),
            )

            if resp["error"]:
                print(f"❌ ERROR: {resp['error'][:80]}")
                scores = {k: 0 for k in test["score_fn"]("").keys()}
                avg = 0
            else:
                scores = test["score_fn"](resp["content"])
                avg = sum(scores.values()) / max(len(scores), 1)
                status = "✅" if avg >= 70 else "⚠️" if avg >= 40 else "❌"
                print(f"{status} avg={avg:.0f}  latency={resp['latency_s']:.1f}s  "
                      f"tokens={resp['tokens_out']}")

            results.append({
                "agent":    test["name"],
                "model":    label,
                "provider": model_info["provider"],
                "scores":   scores,
                "avg":      round(avg, 1),
                "latency":  round(resp["latency_s"], 2),
                "tokens":   resp["tokens_out"],
                "error":    resp["error"],
            })

        print()

    return results


def print_results_table(results: list):
    """Print a comparison table per agent with the winner highlighted."""
    agents = list(dict.fromkeys(r["agent"] for r in results))

    print()
    print("=" * 90)
    print("  RESULTS SUMMARY")
    print("=" * 90)

    recommendations = {}

    for agent in agents:
        agent_results = [r for r in results if r["agent"] == agent]
        agent_results.sort(key=lambda r: r["avg"], reverse=True)

        print(f"\n┌─ {agent} {'─' * (85 - len(agent))}┐")
        print(f"│ {'Model':<25} {'Avg':>5}  {'Latency':>8}  {'Details':<40} │")
        print(f"├{'─' * 88}┤")

        for i, r in enumerate(agent_results):
            marker = "★" if i == 0 and r["avg"] > 0 else " "
            details = "  ".join(f"{k}={v}" for k, v in r["scores"].items())
            if r["error"]:
                details = f"ERROR: {r['error'][:35]}"
            line = (f"│{marker}{r['model']:<24} {r['avg']:>5.0f}  "
                    f"{r['latency']:>7.1f}s  {details[:40]:<40} │")
            print(line)

        print(f"└{'─' * 88}┘")

        winner = agent_results[0] if agent_results[0]["avg"] > 0 else None
        if winner:
            recommendations[agent] = winner
            print(f"  → Winner: {winner['model']} (avg={winner['avg']:.0f}, "
                  f"latency={winner['latency']:.1f}s)")

    # Print recommended config
    print("\n" + "=" * 90)
    print("  RECOMMENDED llm_factory.py CONFIG")
    print("=" * 90)
    for agent, r in recommendations.items():
        print(f"  {agent:<12} → {r['provider']}:{r['model']}")

    return recommendations


def save_results(results: list, recommendations: dict):
    os.makedirs("data", exist_ok=True)
    output = {
        "timestamp": datetime.now().isoformat(),
        "campaign":  CAMPAIGN,
        "models":    [m["label"] for m in MODELS],
        "results":   results,
        "recommendations": {
            agent: {"provider": r["provider"], "model": r["model"], "avg_score": r["avg"]}
            for agent, r in recommendations.items()
        },
    }
    path = "data/benchmark_results.json"
    with open(path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\n  Results saved to {path}")


if __name__ == "__main__":
    results = run_benchmark()
    recommendations = print_results_table(results)
    save_results(results, recommendations)