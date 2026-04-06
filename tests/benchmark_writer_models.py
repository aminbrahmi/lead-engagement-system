"""
benchmark_writer_models.py — teste 4 modèles sur la génération d'emails B2B.

Scoring (5 critères × 10 pts = 50 max):
  1. Spécificité    — cite un fait réel (funding, nom, date)
  2. No filler      — aucune phrase générique
  3. Icebreaker     — ouvre sur le post LinkedIn ou la news
  4. CTA doux       — appel 15 min sans pression
  5. Sujet précis   — ≤ 8 mots + nom de l'entreprise

Run: python -m tests.benchmark_writer_models
"""

import os, re, json, time
from groq import Groq
from dotenv import load_dotenv
load_dotenv()

# ── 4 modèles à tester ────────────────────────────────────────────────────────

MODELS = [
    ("openai/gpt-oss-120b",     "reasoning"),
    ("openai/gpt-oss-20b",      "reasoning"),
    ("llama-3.3-70b-versatile", "standard"),
    ("gemini-2.5-flash",        "google"),    # nécessite GOOGLE_API_KEY
]

# ── Lead de test avec insights réels ─────────────────────────────────────────

LEAD = {
    "name":    "Lennart von Hardenberg",
    "company": "GeneralMind",
    "role":    "CTO",
    "insights": {
        "recent_news":       "GeneralMind a levé 12M$ pre-seed en janvier 2026 (Lakestar, Leo Capital).",
        "person_highlights": "A publié 'AI Agents as Defensible Moats' sur LinkedIn en février 2024.",
        "company_challenge": "Intégrer l'IA avec des systèmes ERP et legacy hétérogènes.",
        "icebreaker":        "Ton post 'AI Agents as Defensible Moats' a mis le doigt sur le problème de l'audit trail que la plupart des vendors ignorent.",
        "value_angle":       "Connecteurs ERP pré-construits et pipelines conformes pour réduire le time-to-market.",
    },
}

CAMPAIGN = "Contacter les CTOs de startups IA à Berlin ayant levé des fonds ces 6 derniers mois."

PROMPT = """Campaign: {campaign}

Lead: {name}, {role} chez {company}
News récente: {recent_news}
Personne: {person_highlights}
Challenge: {company_challenge}
Icebreaker: {icebreaker}
Valeur: {value_angle}

Rédige un email de prospection froid.
- Sujet : ≤ 8 mots, inclure le nom de l'entreprise
- Corps : 4 phrases maximum
- Phrase 1 : utiliser l'icebreaker (post LinkedIn ou news)
- Phrase 4 : CTA doux — appel 15 min, sans pression
- Signe : [Votre Prénom]
- Ton : direct, entre pairs, zéro remplissage

Retourne UNIQUEMENT du JSON brut : {{"subject": "...", "body": "..."}}"""

# ── Listes de détection ───────────────────────────────────────────────────────

FILLER = [
    "i came across", "i hope this", "touch base", "circle back",
    "i wanted to reach out", "just wanted to", "synergies",
    "thought leader", "i'm reaching out", "as per",
]

ICEBREAKERS = [
    "defensible moats", "linkedin", "post", "article",
    "12m", "12 m", "lakestar", "pre-seed", "levé", "funding",
]

CTA_GOOD = [
    "15-minute", "15 minute", "15 min", "quick call", "quick chat",
    "if you're open", "let me know", "no pressure", "open to a",
    "would you be open", "happy to",
]

CTA_BAD = [
    "schedule a demo", "book a meeting", "click here",
    "sign up", "free trial", "limited time",
]

FACTS = ["12m", "lakestar", "leo capital", "2026", "generalmind",
         "epr", "erp", "defensible", "audit trail", "pre-seed"]

# ── Scoring ───────────────────────────────────────────────────────────────────

def score_email(email: dict) -> dict:
    full = f"{email['subject']} {email['body']}".lower()
    co   = LEAD["company"].lower()

    # 1. Spécificité — au moins 2 faits réels
    hits = sum(1 for f in FACTS if f in full)
    spec = 10 if hits >= 2 else (5 if hits == 1 else 0)

    # 2. No filler
    nofl = 0 if any(f in full for f in FILLER) else 10

    # 3. Icebreaker en ouverture
    first = email["body"].split(".")[0].lower() if email["body"] else ""
    ice  = 10 if any(k in first for k in ICEBREAKERS) else 0

    # 4. CTA doux
    good = sum(1 for c in CTA_GOOD if c in full)
    bad  = sum(1 for c in CTA_BAD  if c in full)
    cta  = max(0, min(10, good * 5 - bad * 5))

    # 5. Sujet précis
    words = len(email["subject"].split())
    subj  = (10 if words <= 8 and co in email["subject"].lower()
             else 7 if words <= 8
             else 3 if words <= 12
             else 0)

    total = spec + nofl + ice + cta + subj
    return {"spec": spec, "nofl": nofl, "ice": ice, "cta": cta,
            "subj": subj, "total": total}

# ── Appel modèle ──────────────────────────────────────────────────────────────

def call_groq(client: Groq, model: str, kind: str) -> tuple:
    ins = LEAD["insights"]
    prompt = PROMPT.format(
        campaign=CAMPAIGN, name=LEAD["name"],
        role=LEAD["role"], company=LEAD["company"],
        **ins,
    )
    t0 = time.time()
    kwargs = dict(
        model=model, temperature=0.3, max_tokens=350,
        messages=[{"role": "user", "content": prompt}],
    )
    if kind == "reasoning":
        kwargs["reasoning_effort"] = "default"
    try:
        resp    = client.chat.completions.create(**kwargs)
        raw     = re.sub(r"```json|```", "", resp.choices[0].message.content or "").strip()
        latency = int((time.time() - t0) * 1000)
        try:    data = json.loads(raw)
        except:
            m    = re.search(r"\{.*\}", raw, re.DOTALL)
            data = json.loads(m.group(0)) if m else {}
        s = data.get("subject", "").strip()
        b = data.get("body", "").strip()
        if not s or not b:
            return None, f"réponse vide (raw: {raw[:60]!r})", latency
        return {"subject": s, "body": b}, None, latency
    except Exception as e:
        return None, str(e)[:100], int((time.time() - t0) * 1000)


def call_gemini(prompt_text: str) -> tuple:
    try:
        from langchain_google_genai import ChatGoogleGenerativeAI
        from langchain_core.messages import HumanMessage
        t0  = time.time()
        llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            google_api_key=os.getenv("GOOGLE_API_KEY"),
            temperature=0.3,
        )
        ins = LEAD["insights"]
        prompt = PROMPT.format(
            campaign=CAMPAIGN, name=LEAD["name"],
            role=LEAD["role"], company=LEAD["company"],
            **ins,
        )
        resp    = llm.invoke([HumanMessage(content=prompt)])
        raw     = re.sub(r"```json|```", "", resp.content or "").strip()
        latency = int((time.time() - t0) * 1000)
        try:    data = json.loads(raw)
        except:
            m    = re.search(r"\{.*\}", raw, re.DOTALL)
            data = json.loads(m.group(0)) if m else {}
        s = data.get("subject", "").strip()
        b = data.get("body", "").strip()
        if not s or not b:
            return None, f"réponse vide", latency
        return {"subject": s, "body": b}, None, latency
    except Exception as e:
        return None, str(e)[:100], 0

# ── Affichage ─────────────────────────────────────────────────────────────────

BAR = "█"
def bar(val, max_val=10, width=8):
    filled = round(val / max_val * width)
    return BAR * filled + "░" * (width - filled)

def verdict(total):
    if total >= 45: return "Excellent"
    if total >= 35: return "Bon"
    if total >= 25: return "Moyen"
    return "Insuffisant"

def print_result(model, email, err, latency, sc):
    short = model.split("/")[-1]
    print(f"\n  ┌─ {short}  ({latency}ms)")
    if err:
        print(f"  │  ERREUR : {err}")
        print(f"  └─ Score : 0/50")
        return
    print(f"  │  Sujet : {email['subject']}")
    print(f"  │  ─────")
    for line in email["body"].strip().split("\n"):
        if line.strip():
            print(f"  │  {line}")
    print(f"  │  ─────")
    print(f"  │  Spécificité   {bar(sc['spec'])}  {sc['spec']}/10")
    print(f"  │  No filler     {bar(sc['nofl'])}  {sc['nofl']}/10")
    print(f"  │  Icebreaker    {bar(sc['ice'])}  {sc['ice']}/10")
    print(f"  │  CTA doux      {bar(sc['cta'])}  {sc['cta']}/10")
    print(f"  │  Sujet précis  {bar(sc['subj'])}  {sc['subj']}/10")
    print(f"  └─ Total : {sc['total']}/50  — {verdict(sc['total'])}")


def print_table(results):
    W = 70
    print(f"\n{'═'*W}")
    print(f"  RÉSULTATS BENCHMARK — {LEAD['company']} / {LEAD['name']}")
    print(f"{'═'*W}")
    print(f"  {'Modèle':<30} {'Score':>6}  {'Latence':>8}  {'Verdict'}")
    print(f"  {'─'*66}")

    ranked = sorted(results, key=lambda r: -(r["sc"]["total"] if r["sc"] else -1))
    medals = {0:"1.", 1:"2.", 2:"3.", 3:"4."}
    for i, r in enumerate(ranked):
        sc    = r["sc"]
        mark  = ("+" if sc and sc["total"] >= 35 else
                 "~" if sc and sc["total"] >= 20 else
                 "x")
        short = r["model"].split("/")[-1][:29]
        score = f"{sc['total']}/50" if sc else "—"
        lat   = f"{r['latency']}ms" if r["latency"] else "—"
        verd  = verdict(sc["total"]) if sc else f"ERREUR: {(r['err'] or '')[:20]}"
        print(f"  {mark} {short:<30} {score:>6}  {lat:>8}  {verd}")

    print(f"{'═'*W}")
    best = next((r for r in ranked if r["sc"] and r["sc"]["total"] > 0), None)
    if best:
        print(f"\n  Meilleur modèle : {best['model'].split('/')[-1]}")
        print(f"  Score           : {best['sc']['total']}/50")
        print(f"  Latence         : {best['latency']}ms")
        print(f"\n  Ajouter dans .env :")
        print(f"    WRITER_MODEL=groq/{best['model']}")
    print()

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    client  = Groq(api_key=os.getenv("GROQ_API_KEY"))
    results = []

    print(f"\nBenchmark email writer — 4 modèles\n{'─'*40}")

    for model, kind in MODELS:
        if kind == "google":
            email, err, latency = call_gemini(model)
        else:
            email, err, latency = call_groq(client, model, kind)

        sc = score_email(email) if email else None
        results.append({"model": model, "kind": kind,
                        "email": email, "err": err,
                        "latency": latency, "sc": sc})
        print_result(model, email, err, latency, sc or {})

    print_table(results)

if __name__ == "__main__":
    main()