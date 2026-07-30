"""
email_quality_scorer.py — score an email draft (reply likelihood) + actionable
suggestions, using ml/email_quality_model.joblib (trained via
email_quality_scoring_v2.ipynb / train_quality_local.py).

The model was trained on engineered features. At inference we DERIVE those same
features from the raw subject/body (+ optional lead context for personalization),
so the API only needs the text a user is writing.

Loads defensively: on any failure it degrades to {"available": False} instead of
crashing the request.
"""
import os
import re

_MODEL = None
_LOAD_FAILED = False
_MODEL_PATH = os.path.join(os.path.dirname(__file__), "email_quality_model.joblib")

# ── keyword banks used to derive features from raw text ──────────────────────
CTA_PHRASES = [
    "book", "schedule", "demo", "meeting", "calendar", "let me know", "reply",
    "connect", "chat", "available", "grab a", "hop on", "set up", "catch up",
    "worth a", "interested", "learn more", "sign up", "get started", "book a slot",
    "free trial", "would you be open", "quick call", "15 min", "15-min", "a call",
    "your thoughts", "happy to", "slot",
]
# Only *unambiguously* promotional phrases — legit B2B copy uses "offer", "free",
# "amazing" etc. in normal sentences, so those alone must NOT flag an email as spammy.
STRONG_SPAM = [
    "act now", "limited time", "click here", "buy now", "risk-free", "100% free",
    "money back", "cash bonus", "order now", "act fast", "amazing offer",
    "exclusive deal", "don't miss out", "winner", "congratulations you've",
]
FORMAL_MARKERS = [
    "dear ", "sincerely", "best regards", "kind regards", "yours faithfully",
    "yours sincerely", "to whom it may concern", "regards,",
]


# ── feature derivation ───────────────────────────────────────────────────────
def _length_bucket(wc: int) -> str:
    if wc < 66:
        return "short"
    if wc <= 110:
        return "medium"
    return "long"


def _is_user_spammy(subject: str, body: str, num_excl: int) -> bool:
    """Unambiguous, user-introduced spam signals (shouting or promo phrases).
    A brand name in caps (e.g. 'TALAN') is NOT spam, so we count DISTINCT all-caps
    words and require several — a single repeated name never trips it."""
    text = f"{subject} {body}"
    low = text.lower()
    distinct_caps = len(set(re.findall(r"\b[A-Z]{4,}\b", text)))
    return num_excl >= 3 or distinct_caps >= 3 or any(p in low for p in STRONG_SPAM)


def _tone(subject: str, body: str, num_excl: int) -> str:
    if _is_user_spammy(subject, body, num_excl):
        return "spammy"
    if any(m in f"{subject} {body}".lower() for m in FORMAL_MARKERS):
        return "formal"
    return "casual"


def _company_token(company: str) -> str:
    """First significant token of a company name, without a TLD suffix.
    'Noon.com' -> 'noon', 'Yoox Net-a-Porter' -> 'yoox'."""
    c = re.sub(r"\.(com|io|ai|co|net|org|app|dev)$", "", (company or "").strip().lower())
    parts = re.split(r"[\s,\-]+", c)
    return parts[0] if parts and parts[0] else ""


def _personalization(subject: str, body: str, lead) -> int:
    text = f"{subject} {body}"
    low = text.lower()
    if lead:
        name = str(lead.get("name") or "").strip().lower()
        first = name.split()[0] if name and name != "unknown" else ""
        token = _company_token(lead.get("company") or "")
        has_name = bool(first) and first in low
        has_company = bool(token) and token in low
        if has_name and has_company:
            return 2          # greeting by name + company referenced = fully personalized
        if has_name or has_company:
            return 1
        return 0
    # no lead context → infer from a personalized greeting
    if re.search(r"\b(hi|hello|hey|dear)\s+[A-Z][a-z]+", text):
        return 1
    return 0


def derive_features(subject: str, body: str, lead=None, hints=None) -> dict:
    """Derive the model features from raw text.

    `hints` carries the *author's intent* (from the Writer agent) for the few
    semantic features heuristics get wrong — personalization, tone, CTA. We trust
    those hints, EXCEPT tone: if the current text is unambiguously spammy the user
    made it so, and the live text wins.
    """
    subject = subject or ""
    body = body or ""
    wc = len(body.split())
    num_excl = body.count("!")
    feats = {
        "word_count":            wc,
        "has_question":          int("?" in body),
        "has_cta":               int(any(p in f"{subject} {body}".lower() for p in CTA_PHRASES)),
        "has_link":              int("http" in body.lower() or "www." in body.lower()),
        "personalization_level": _personalization(subject, body, lead),
        "num_exclamations":      num_excl,
        "tone":                  _tone(subject, body, num_excl),
        "length_bucket":         _length_bucket(wc),
    }
    if hints:
        if "personalization_level" in hints:
            feats["personalization_level"] = int(hints["personalization_level"])
        if "has_cta" in hints:
            feats["has_cta"] = int(hints["has_cta"])
        # Trust the Writer's declared tone UNLESS the user has clearly made the
        # text spammy (shouting / promo phrases). A weak signal like a brand name
        # in caps must not override the author's intent.
        if "tone" in hints and not _is_user_spammy(subject, body, num_excl):
            feats["tone"] = hints["tone"]
    return feats


# ── suggestion engine (mirrors notebook §7, uses the model's coef_map) ───────
def _coef(coef_map: dict, name: str, default=0.0) -> float:
    for k, v in coef_map.items():
        if k.endswith(name):
            return float(v)
    return default


def build_suggestions(feat: dict, coef_map: dict, top_n: int = 3) -> list:
    cand = []
    if feat["has_question"] == 0 and _coef(coef_map, "has_question") > 0:
        cand.append((abs(_coef(coef_map, "has_question")),
                     "Add a question to prompt a reply (e.g. 'Would this be useful for your team?')."))
    if feat["has_cta"] == 0 and _coef(coef_map, "has_cta") > 0:
        cand.append((abs(_coef(coef_map, "has_cta")),
                     "Add a clear call-to-action (e.g. 'Would you be open to a 15-min call?')."))
    if feat["personalization_level"] < 2 and _coef(coef_map, "personalization_level") > 0:
        cand.append((abs(_coef(coef_map, "personalization_level")),
                     "Personalize further — mention the company name and a specific pain point."))
    if feat["length_bucket"] == "long" and _coef(coef_map, "length_bucket_long") < 0:
        cand.append((abs(_coef(coef_map, "length_bucket_long")),
                     "Shorten the email — long emails get fewer replies."))
    if feat["length_bucket"] == "medium" and _coef(coef_map, "length_bucket_short") > 0 and feat["word_count"] > 90:
        cand.append((abs(_coef(coef_map, "length_bucket_short")) * 0.5,
                     "Consider trimming the email further for a punchier, shorter pitch."))
    if feat["tone"] == "spammy" and _coef(coef_map, "tone_spammy") < 0:
        cand.append((abs(_coef(coef_map, "tone_spammy")),
                     "Avoid urgent/spammy language (e.g. 'ACT NOW', 'AMAZING OFFER')."))
    if feat["num_exclamations"] >= 1 and _coef(coef_map, "num_exclamations") < 0:
        cand.append((abs(_coef(coef_map, "num_exclamations")),
                     "Reduce exclamation marks — they read as pushy."))
    if feat["has_link"] == 1 and _coef(coef_map, "has_link") < 0:
        cand.append((abs(_coef(coef_map, "has_link")),
                     "Consider removing the direct link on a first-touch email — it can read as spammy."))
    cand.sort(key=lambda x: x[0], reverse=True)
    return [m for _, m in cand[:top_n]] or ["Looks solid — no major red flags detected."]


# ── model loading + scoring ──────────────────────────────────────────────────
def is_available() -> bool:
    return os.path.exists(_MODEL_PATH)


def _load_model():
    global _MODEL, _LOAD_FAILED
    if _MODEL is None and not _LOAD_FAILED and is_available():
        try:
            import joblib
            _MODEL = joblib.load(_MODEL_PATH)
        except Exception as e:
            _LOAD_FAILED = True
            print(f"[QualityScorer] model load failed — retrain locally "
                  f"(python ml/train_quality_local.py): {e}")
    return _MODEL


def score_email(subject: str, body: str, lead=None, hints=None) -> dict:
    """Return {available, score(0-100), suggestions[], features{}}."""
    feats = derive_features(subject, body, lead, hints)
    model = _load_model()
    if not model:
        return {"available": False, "features": feats}
    try:
        import pandas as pd
        row = pd.DataFrame([{**feats, "full_text": f"{subject or ''} . {body or ''}"}])
        proba = float(model["pipeline"].predict_proba(row)[:, 1][0])
        suggestions = build_suggestions(feats, model.get("coef_map", {}))
        return {
            "available": True,
            "score": round(proba * 100, 1),
            "suggestions": suggestions,
            "features": feats,
        }
    except Exception as e:
        print(f"[QualityScorer] scoring failed: {e}")
        return {"available": False, "features": feats}
