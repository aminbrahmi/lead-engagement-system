"""
email_generator_node.py — generate a personalized cold email for each lead.

Uses the structured insights from enricher_node to write emails that:
  - Open with a specific, real reference (not "I came across your profile")
  - State a relevant value proposition tied to their actual challenge
  - Have a soft, low-friction CTA
  - Feel human, not AI-generated

Runs all generations concurrently.
"""

import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

from langchain_core.messages import HumanMessage, SystemMessage

from agents.llm_factory import get_writer_llm


_SYSTEM = (
    "You are an expert B2B cold email copywriter. "
    "You write short, specific, human emails that get replies. "
    "You NEVER use generic openers like 'I came across your profile' or "
    "'I hope this finds you well'. Every sentence earns its place."
)


def _email_prompt(lead: dict, campaign_prompt: str) -> str:
    insights = lead.get("insights", {})
    return f"""Campaign goal: {campaign_prompt}

Lead:
  Name:    {lead.get('name')}
  Role:    {lead.get('role')}
  Company: {lead.get('company')}
  Email:   {lead.get('email')}

Research insights:
  Recent news:       {insights.get('recent_news', 'N/A')}
  Person highlights: {insights.get('person_highlights', 'N/A')}
  Company challenge: {insights.get('company_challenge', 'N/A')}
  Tech stack:        {insights.get('tech_stack', 'N/A')}
  Icebreaker:        {insights.get('icebreaker', 'N/A')}
  Value angle:       {insights.get('value_angle', 'N/A')}

Write a cold outreach email. Rules:
  - Subject line: specific, no clickbait, max 8 words
  - Body: 4-6 sentences MAX
  - Line 1: reference the icebreaker or recent news — something SPECIFIC and REAL
  - Line 2-3: connect their challenge to what you offer (use value_angle)
  - Line 4: ultra-soft CTA — suggest a 15-min call, no pressure
  - Tone: direct, peer-to-peer, zero fluff
  - Sign off with just the sender's first name placeholder: [Your Name]

Return ONLY raw JSON (no fences):
{{
  "subject": "...",
  "body": "..."
}}"""


def _generate_one(lead: dict, campaign_prompt: str) -> dict:
    name    = lead.get("name", "")
    company = lead.get("company", "")

    # Skip cold leads or missing insights
    if lead.get("segment") == "cold" or not lead.get("insights"):
        return lead

    # Skip if ALL insight values are empty/N/A (no research found)
    insights = lead.get("insights", {})
    real_values = [
        v for v in insights.values()
        if v and v.strip().lower() not in (
            "n/a", "no recent news found.", "no public statements or articles found.",
            "no specific challenge identified.", "no information on technologies used.",
            "no specific detail available.", "no actionable value angle identified.",
            "not found", "unknown", ""
        )
    ]
    if len(real_values) < 2:
        print(f"[EmailGen] ✗ Skipping {lead.get('company')} — insights too thin to personalize")
        return lead

    print(f"[EmailGen] Writing email for {name} @ {company}…")

    llm      = get_writer_llm()
    response = llm.invoke([
        SystemMessage(content=_SYSTEM),
        HumanMessage(content=_email_prompt(lead, campaign_prompt)),
    ])

    content = response.content
    if isinstance(content, list):
        content = "\n".join(
            b["text"] for b in content
            if isinstance(b, dict) and b.get("type") == "text"
        )

    content = re.sub(r'```json|```', '', content or '').strip()
    # Remove invalid control characters that break JSON parsing (e.g. unescaped \n in strings)
    content = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', content)

    try:
        email_data = json.loads(content)
    except Exception:
        # Try extracting just the JSON object
        match = re.search(r'\{[^{}]*"subject"[^{}]*"body"[^{}]*\}', content, re.DOTALL)
        if not match:
            match = re.search(r'\{.*\}', content, re.DOTALL)
        if match:
            clean = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', match.group(0))
            try:
                email_data = json.loads(clean)
            except Exception:
                # Last resort: extract subject and body manually
                s = re.search(r'"subject"\s*:\s*"([^"]+)"', content)
                b = re.search(r'"body"\s*:\s*"(.*?)"(?:\s*\})', content, re.DOTALL)
                email_data = {
                    "subject": s.group(1) if s else "",
                    "body":    b.group(1).replace("\\n", "\n") if b else "",
                }
        else:
            email_data = {}

    lead = dict(lead)
    lead["draft_email"] = email_data
    print(f"[EmailGen] ✓ Email written for {company}")
    return lead


def run_email_generator(enriched_leads: list[dict], campaign_prompt: str) -> list[dict]:
    """Generate personalized emails for all HOT/WARM leads concurrently."""
    to_generate = [l for l in enriched_leads
                   if l.get("segment") in ("hot", "warm") and l.get("insights")]
    rest        = [l for l in enriched_leads if l not in to_generate]

    if not to_generate:
        print("[EmailGen] No leads to generate emails for.")
        return enriched_leads

    print(f"[EmailGen] Generating {len(to_generate)} emails concurrently…")
    result_map: dict[int, dict] = {}

    with ThreadPoolExecutor(max_workers=4) as pool:
        future_map = {
            pool.submit(_generate_one, l, campaign_prompt): i
            for i, l in enumerate(to_generate)
        }
        for future in as_completed(future_map):
            idx             = future_map[future]
            result_map[idx] = future.result()

    generated = [result_map[i] for i in sorted(result_map)]
    return generated + rest