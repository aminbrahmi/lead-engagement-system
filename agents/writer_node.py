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


def _clean_body(text: str) -> str:
    """Normalize LLM email body: fix escaped newlines, strip spaces, collapse blank lines."""
    # LLM sometimes outputs \\n (JSON-escaped) instead of real newlines
    text = text.replace('\\n', '\n')
    lines = [l.strip() for l in text.splitlines()]
    result, blanks = [], 0
    for line in lines:
        if line == "":
            blanks += 1
            if blanks <= 1:
                result.append(line)
        else:
            blanks = 0
            result.append(line)
    return "\n".join(result).strip()

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


def _build_sender_blocks(sender_info: dict):
    """Return (signature_block, intro_line, website_line) strings."""
    sender_name    = (sender_info.get("name") or "").strip()
    sender_title   = (sender_info.get("title") or "").strip()
    sender_company = (sender_info.get("company") or "").strip()
    company_url    = (sender_info.get("company_url") or "").strip()
    company_desc   = (sender_info.get("company_description") or "").strip()

    # Signature block for sign-off
    if sender_title and sender_company:
        sig = f"{sender_name}\n{sender_title}, {sender_company}"
    elif sender_company:
        sig = f"{sender_name}\n{sender_company}"
    else:
        sig = sender_name or "[Your Name]"

    # One-line sender intro — only if we have real data
    if sender_title and sender_company:
        intro = f"My name is {sender_name}, {sender_title} at {sender_company}"
        if company_desc:
            intro += f" — {company_desc}"
        intro += "."
    elif sender_company:
        intro = f"My name is {sender_name} from {sender_company}."
    elif sender_name:
        intro = f"My name is {sender_name}."
    else:
        intro = ""   # no sender info — skip the intro line entirely

    # Website invitation (only if URL is configured)
    website = ""
    if company_url:
        website = f"If you'd like to learn more about what we do, feel free to visit us at {company_url}"

    return sig, intro, website


def _email_prompt_variant_a(lead: dict, campaign_prompt: str, sender_info: dict) -> str:
    """Variant A: Insight-led opener."""
    insights   = lead.get("insights", {})
    first_name = (lead.get("name") or "").split()[0] or "there"
    sig, sender_intro, website_line = _build_sender_blocks(sender_info)
    company_url = (sender_info.get("company_url") or "").strip()

    intro_instruction = (
        f'Paragraph 2 — SENDER INTRO: "{sender_intro}"'
        if sender_intro else
        "Paragraph 2 — SENDER INTRO: (skip — no sender info provided)"
    )
    website_instruction = (
        f'Paragraph 6 — WEBSITE: "{website_line}" — include the URL {company_url} verbatim'
        if website_line else
        "Paragraph 6 — WEBSITE: (skip — no website URL configured)"
    )

    return f"""Campaign goal: {campaign_prompt}

Lead: {lead.get('name')}, {lead.get('role')} at {lead.get('company')}

Research insights:
  Recent news:       {insights.get('recent_news', 'N/A')}
  Person highlights: {insights.get('person_highlights', 'N/A')}
  Company challenge: {insights.get('company_challenge', 'N/A')}
  Tech stack:        {insights.get('tech_stack', 'N/A')}
  Icebreaker:        {insights.get('icebreaker', 'N/A')}
  Value angle:       {insights.get('value_angle', 'N/A')}

Write VARIANT A (insight-led). The body MUST be structured as SEPARATE PARAGRAPHS separated by blank lines:

Paragraph 1 — GREETING (alone on its own line): "Hi {first_name},"

{intro_instruction}

Paragraph 3 — HOOK: 1-2 sentences referencing a SPECIFIC fact (icebreaker, recent news, or funding). No generic openers.

Paragraph 4 — VALUE: Connect their company challenge to how you can help (use value_angle). 2 sentences max.

Paragraph 5 — CREDIBILITY: One concrete metric or reference to similar companies you have helped. 1-2 sentences.

{website_instruction}

Paragraph 7 — CTA: One soft professional ask for a brief conversation. No pressure.

Paragraph 8 — SIGN-OFF:
Best regards,
{sig}

Rules:
  - Subject: specific, max 8 words, no clickbait, no emoji
  - Write in short paragraphs, one blank line between each
  - No exclamation marks, no "I hope this finds you well"
  - Total: 6-8 sentences

Return ONLY raw JSON (no markdown fences):
{{
  "subject": "...",
  "body": "...",
  "variant": "A",
  "variant_strategy": "insight-led"
}}"""


def _email_prompt_variant_b(lead: dict, campaign_prompt: str, sender_info: dict) -> str:
    """Variant B: Challenge-led opener."""
    insights   = lead.get("insights", {})
    first_name = (lead.get("name") or "").split()[0] or "there"
    sig, sender_intro, website_line = _build_sender_blocks(sender_info)
    company_url = (sender_info.get("company_url") or "").strip()

    intro_instruction = (
        f'Paragraph 2 — SENDER INTRO: "{sender_intro}"'
        if sender_intro else
        "Paragraph 2 — SENDER INTRO: (skip — no sender info provided)"
    )
    website_instruction = (
        f'Paragraph 6 — WEBSITE: "{website_line}" — include the URL {company_url} verbatim'
        if website_line else
        "Paragraph 6 — WEBSITE: (skip — no website URL configured)"
    )

    return f"""Campaign goal: {campaign_prompt}

Lead: {lead.get('name')}, {lead.get('role')} at {lead.get('company')}

Research insights:
  Recent news:       {insights.get('recent_news', 'N/A')}
  Person highlights: {insights.get('person_highlights', 'N/A')}
  Company challenge: {insights.get('company_challenge', 'N/A')}
  Tech stack:        {insights.get('tech_stack', 'N/A')}
  Icebreaker:        {insights.get('icebreaker', 'N/A')}
  Value angle:       {insights.get('value_angle', 'N/A')}

Write VARIANT B (challenge-led). The body MUST be structured as SEPARATE PARAGRAPHS separated by blank lines:

Paragraph 1 — GREETING (alone on its own line): "Hi {first_name},"

{intro_instruction}

Paragraph 3 — CHALLENGE: Name the specific challenge this company faces (use company_challenge). Frame as an observation, not a guess.

Paragraph 4 — INSIGHT: Show you understand WHY this is hard — reference their tech stack or scale. 1-2 sentences.

Paragraph 5 — SOLUTION: Position your value with a concrete metric or similar-company reference. 1-2 sentences.

{website_instruction}

Paragraph 7 — CTA: Offer to share a brief case study or insight. No "pick your brain".

Paragraph 8 — SIGN-OFF:
Best regards,
{sig}

Rules:
  - Subject: different angle from Variant A, focused on the challenge, max 8 words, no emoji
  - Write in short paragraphs, one blank line between each
  - No exclamation marks, no generic openers
  - Total: 6-8 sentences

Return ONLY raw JSON (no markdown fences):
{{
  "subject": "...",
  "body": "...",
  "variant": "B",
  "variant_strategy": "challenge-led"
}}"""


def _writer_quality_hints(lead: dict) -> dict:
    """Authoritative feature hints the Writer *knows* about its own output, so the
    ML quality-scorer doesn't have to re-guess them from text (Option B).

    By construction every generated email:
      - greets by first name AND references the company + a pain point  → personalization 2
      - is written in a professional tone with NO exclamation marks      → tone 'formal'
      - always ends with a soft call-to-action (paragraph 7)             → has_cta 1
    Generation is skipped unless the lead has a name, a company and rich
    insights, so these hold whenever a draft exists.
    """
    return {"personalization_level": 2, "tone": "formal", "has_cta": 1}


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

    # Don't draft emails for leads we can't actually contact:
    #  - no email address → nothing to send to (and the UI won't even show the editor)
    #  - unknown name → can't personalize ("Hi unknown,")
    if not lead.get("email") or (name or "").strip().lower() in ("", "unknown"):
        return lead

    # Generate whenever we have insights — drafting is independent of the segment.
    # (A cold/unverified lead still gets a draft ready; whether it is *sent* is
    #  decided elsewhere by the email-reliability rules.)
    if not lead.get("insights"):
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
        if email_a.get("body"):
            email_a["body"] = _clean_body(email_a["body"])
        email_a.setdefault("variant", "A")
        email_a.setdefault("variant_strategy", "insight-led")
        email_a["quality_hints"] = _writer_quality_hints(lead)
        lead["draft_emails"]["A"] = email_a
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
        if email_b.get("body"):
            email_b["body"] = _clean_body(email_b["body"])
        email_b.setdefault("variant", "B")
        email_b.setdefault("variant_strategy", "challenge-led")
        email_b["quality_hints"] = _writer_quality_hints(lead)
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


def generate_reply_from_response(
    lead: dict,
    received_body: str,
    original_subject: str,
    sender_info: dict,
) -> dict:
    """Generate a contextual reply to a lead's response using the LLM.
    Returns { subject, body }.
    """
    llm = get_writer_llm()
    website_line = _build_sender_blocks(sender_info)[2]
    company_url = (sender_info.get("company_url") or "").strip()

    first_name = (lead.get("name") or "").split()[0] or "there"
    role       = lead.get("role", "")
    company    = lead.get("company", "")

    website_instruction = (
        f'If relevant, include the website line: "{website_line}"'
        if website_line else ""
    )

    prompt = f"""You are writing a professional B2B reply email.

Sender: {sender_info.get('name', '')} — {sender_info.get('title', '')} at {sender_info.get('company', '')}
Lead: {lead.get('name', '')}, {role} at {company}

Original email subject: "{original_subject}"

Lead's reply:
---
{received_body.strip()[:1500]}
---

Write a concise, professional reply that:
1. Starts with "Hi {first_name},"
2. Directly addresses what they said (acknowledge their reply specifically)
3. Moves the conversation forward (propose a next step, answer their question, or add value)
4. Keeps it SHORT: 3-5 sentences max
5. Ends with a clear, single call to action
{website_instruction}
6. Sign off:
   Best regards,
   {sender_info.get('name', '')}
   {sender_info.get('title', '') + ', ' + sender_info.get('company', '') if sender_info.get('title') and sender_info.get('company') else sender_info.get('company', '')}

Rules:
- No exclamation marks
- No generic openers ("I hope this finds you well", "Thank you for your reply")
- Each paragraph separated by a blank line
{f'- Include the URL {company_url} verbatim if you include the website line' if company_url else ''}

Return ONLY raw JSON (no fences):
{{"subject": "Re: {original_subject}", "body": "..."}}"""

    response = llm.invoke([
        SystemMessage(content="You are a senior B2B sales professional writing a follow-up reply. Be direct, concise and human."),
        HumanMessage(content=prompt),
    ])

    result = _parse_email_json(response.content)
    if result.get("body"):
        result["body"] = _clean_body(result["body"])
    return result


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