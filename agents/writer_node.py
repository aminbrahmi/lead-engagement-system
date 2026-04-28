"""
writer_node.py — generate A/B personalized cold emails for each lead.

Generates TWO email variants per lead:
  - Variant A: insight-led opener (leads with the icebreaker fact)
  - Variant B: challenge-led opener (leads with the company problem)

Both variants are professional, structured, and human.
Runs all generations concurrently.
"""

import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

from langchain_core.messages import HumanMessage, SystemMessage

from agents.llm_factory import get_writer_llm


_SYSTEM = (
    "You are a senior B2B outreach strategist who writes emails for C-level executives. "
    "Your emails are professional, concise, and structured — not casual or sloppy. "
    "Every email must feel like it was written by a knowledgeable peer, not a sales bot. "
    "You NEVER use generic openers like 'I came across your profile' or 'I hope this finds you well'. "
    "You NEVER use exclamation marks. "
    "Every sentence must earn its place. "
    "Format: short paragraphs, no bullet points in the email body."
)


def _email_prompt_variant_a(lead: dict, campaign_prompt: str, sender_info: dict) -> str:
    """Variant A: Insight-led opener — leads with a specific fact."""
    insights = lead.get("insights", {})
    sender_name = sender_info.get("name", "[Your Name]")
    sender_title = sender_info.get("title", "")
    sender_company = sender_info.get("company", "")

    signature_block = sender_name
    if sender_title and sender_company:
        signature_block = f"{sender_name}\n{sender_title}, {sender_company}"
    elif sender_company:
        signature_block = f"{sender_name}\n{sender_company}"

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

Write VARIANT A — the "insight-led" cold email. Rules:
  - Subject line: specific, professional, max 8 words, no clickbait, no emojis
  - Opening line: reference a SPECIFIC fact — the recent news, funding, or icebreaker
  - Second paragraph: connect their specific challenge to what you can help with (use value_angle)
  - Third paragraph: brief credibility — mention similar companies helped or a concrete metric
  - Closing: professional soft CTA — suggest a brief conversation, no pressure language
  - Tone: executive peer-to-peer, confident but not pushy, zero fluff
  - Length: 5-7 sentences across 3-4 short paragraphs
  - No exclamation marks, no "I hope this finds you well", no "I came across"
  - Sign off with:
    Best regards,
    {signature_block}

Return ONLY raw JSON (no fences):
{{
  "subject": "...",
  "body": "...",
  "variant": "A",
  "variant_strategy": "insight-led"
}}"""


def _email_prompt_variant_b(lead: dict, campaign_prompt: str, sender_info: dict) -> str:
    """Variant B: Challenge-led opener — leads with the company problem."""
    insights = lead.get("insights", {})
    sender_name = sender_info.get("name", "[Your Name]")
    sender_title = sender_info.get("title", "")
    sender_company = sender_info.get("company", "")

    signature_block = sender_name
    if sender_title and sender_company:
        signature_block = f"{sender_name}\n{sender_title}, {sender_company}"
    elif sender_company:
        signature_block = f"{sender_name}\n{sender_company}"

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

Write VARIANT B — the "challenge-led" cold email. Rules:
  - Subject line: different from variant A, focused on the challenge/problem, max 8 words
  - Opening line: name a specific challenge their company faces (use company_challenge) — frame it as an observation, not a guess
  - Second paragraph: show you understand WHY this is hard (reference their tech stack or scale)
  - Third paragraph: position your solution with a concrete metric or case study reference
  - Closing: professional CTA — offer to share a relevant case study or brief insight, no "pick your brain"
  - Tone: consultative expert, slightly more analytical than Variant A
  - Length: 5-7 sentences across 3-4 short paragraphs
  - No exclamation marks, no generic openers
  - Sign off with:
    Best regards,
    {signature_block}

Return ONLY raw JSON (no fences):
{{
  "subject": "...",
  "body": "...",
  "variant": "B",
  "variant_strategy": "challenge-led"
}}"""


def _parse_email_json(content: str) -> dict:
    """4-level JSON parsing — same robust logic as before."""
    if isinstance(content, list):
        content = "\n".join(
            b["text"] for b in content
            if isinstance(b, dict) and b.get("type") == "text"
        )

    content = re.sub(r'```json|```', '', content or '').strip()
    content = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', content)

    # Level 1: direct parse
    try:
        return json.loads(content)
    except Exception:
        pass

    # Level 2: regex for {..."subject"..."body"...}
    match = re.search(r'\{[^{}]*"subject"[^{}]*"body"[^{}]*\}', content, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except Exception:
            pass

    # Level 3: generic {...}
    match = re.search(r'\{.*\}', content, re.DOTALL)
    if match:
        clean = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', match.group(0))
        try:
            return json.loads(clean)
        except Exception:
            pass

    # Level 4: manual extraction
    s = re.search(r'"subject"\s*:\s*"([^"]+)"', content)
    b = re.search(r'"body"\s*:\s*"(.*?)"(?:\s*[,}])', content, re.DOTALL)
    return {
        "subject": s.group(1) if s else "",
        "body": b.group(1).replace("\\n", "\n") if b else "",
    }


def _generate_one(lead: dict, campaign_prompt: str, sender_info: dict) -> dict:
    name = lead.get("name", "")
    company = lead.get("company", "")

    # Skip cold leads or missing insights
    if lead.get("segment") == "cold" or not lead.get("insights"):
        return lead

    # Skip if ALL insight values are empty/N/A
    insights = lead.get("insights", {})
    empty_markers = {
        "n/a", "no information found.", "no public statements or articles found.",
        "no specific challenge identified.", "no information on technologies used.",
        "no specific detail available.", "no actionable value angle identified.",
        "not found", "unknown", ""
    }
    real_values = [
        v for v in insights.values()
        if isinstance(v, str) and v.strip().lower() not in empty_markers and len(v.strip()) >= 15
    ]
    if len(real_values) < 2:
        print(f"[EmailGen] ✗ Skipping {company} — insights too thin to personalize")
        return lead

    print(f"[EmailGen] Writing A/B emails for {name} @ {company}…")

    llm = get_writer_llm()
    lead = dict(lead)
    lead["draft_emails"] = {}

    # ── Generate Variant A ────────────────────────────────────────────────────
    try:
        response_a = llm.invoke([
            SystemMessage(content=_SYSTEM),
            HumanMessage(content=_email_prompt_variant_a(lead, campaign_prompt, sender_info)),
        ])
        email_a = _parse_email_json(response_a.content)
        email_a.setdefault("variant", "A")
        email_a.setdefault("variant_strategy", "insight-led")
        lead["draft_emails"]["A"] = email_a
        # Keep backward compat — draft_email = variant A
        lead["draft_email"] = email_a
        print(f"[EmailGen] ✓ Variant A written for {company}: {email_a.get('subject', '?')}")
    except Exception as e:
        print(f"[EmailGen] ⚠ Variant A failed for {company}: {e}")

    # ── Generate Variant B ────────────────────────────────────────────────────
    try:
        response_b = llm.invoke([
            SystemMessage(content=_SYSTEM),
            HumanMessage(content=_email_prompt_variant_b(lead, campaign_prompt, sender_info)),
        ])
        email_b = _parse_email_json(response_b.content)
        email_b.setdefault("variant", "B")
        email_b.setdefault("variant_strategy", "challenge-led")
        lead["draft_emails"]["B"] = email_b
        print(f"[EmailGen] ✓ Variant B written for {company}: {email_b.get('subject', '?')}")
    except Exception as e:
        print(f"[EmailGen] ⚠ Variant B failed for {company}: {e}")

    if not lead.get("draft_emails"):
        print(f"[EmailGen] ✗ Both variants failed for {company}")
    else:
        count = len(lead["draft_emails"])
        print(f"[EmailGen] ✓ {count} variant(s) ready for {company}")

    return lead


def run_email_generator(
    enriched_leads: list[dict],
    campaign_prompt: str,
    sender_info: dict = None,
) -> list[dict]:
    """Generate A/B personalized emails for all HOT/WARM leads concurrently."""
    if sender_info is None:
        sender_info = {"name": "[Your Name]", "title": "", "company": ""}

    to_generate = [
        l for l in enriched_leads
        if l.get("segment") in ("hot", "warm") and l.get("insights")
    ]
    rest = [l for l in enriched_leads if l not in to_generate]

    if not to_generate:
        print("[EmailGen] No leads to generate emails for.")
        return enriched_leads

    print(f"[EmailGen] Generating A/B emails for {len(to_generate)} leads concurrently…")
    result_map: dict[int, dict] = {}

    with ThreadPoolExecutor(max_workers=4) as pool:
        future_map = {
            pool.submit(_generate_one, l, campaign_prompt, sender_info): i
            for i, l in enumerate(to_generate)
        }
        for future in as_completed(future_map):
            idx = future_map[future]
            try:
                result_map[idx] = future.result()
            except Exception as e:
                print(f"[EmailGen] ⚠ Lead {idx} failed: {e}")
                result_map[idx] = to_generate[idx]

    generated = [result_map[i] for i in sorted(result_map)]
    return generated + rest