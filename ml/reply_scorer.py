"""
reply_scorer.py — load the trained LightGBM model and score leads by reply probability.

Reproduces the exact `build_features` used at training time so the saved Pipeline
(preprocess + model) receives the columns it expects.

Place the trained model at:  ml/lead_reply_model.joblib
"""

import os
import json
import pandas as pd

_MODEL = None
_LOAD_FAILED = False
_MODEL_PATH = os.path.join(os.path.dirname(__file__), "lead_reply_model.joblib")


CITY_TO_COUNTRY = {
    "berlin": "Germany", "munich": "Germany", "hamburg": "Germany", "germany": "Germany",
    "singapore": "Singapore", "london": "UK", "manchester": "UK", "cambridge": "UK",
    "basingstoke": "UK", "uk": "UK", "dubai": "UAE", "abu dhabi": "UAE", "uae": "UAE",
    "paris": "France", "lyon": "France", "toulouse": "France", "france": "France",
    "milan": "Italy", "rome": "Italy", "turin": "Italy", "bologna": "Italy", "italy": "Italy",
    "madrid": "Spain", "barcelona": "Spain", "valencia": "Spain", "spain": "Spain",
    "amsterdam": "Netherlands", "rotterdam": "Netherlands", "utrecht": "Netherlands", "netherlands": "Netherlands",
    "stockholm": "Sweden", "gothenburg": "Sweden", "malmo": "Sweden", "sweden": "Sweden",
    "tokyo": "Japan", "osaka": "Japan", "yokohama": "Japan", "japan": "Japan",
    "bangalore": "India", "mumbai": "India", "delhi": "India", "hyderabad": "India", "india": "India",
    "sao paulo": "Brazil", "rio de janeiro": "Brazil", "belo horizonte": "Brazil", "brazil": "Brazil",
    "toronto": "Canada", "vancouver": "Canada", "montreal": "Canada", "canada": "Canada",
    "sydney": "Australia", "melbourne": "Australia", "brisbane": "Australia", "australia": "Australia",
    "united states": "USA",
}


def get_country(loc):
    if pd.isna(loc):
        return "Unknown"
    parts = [p.strip() for p in str(loc).split(",")]
    last = parts[-1].lower()
    if last in CITY_TO_COUNTRY:
        return CITY_TO_COUNTRY[last]
    first = parts[0].lower()
    return CITY_TO_COUNTRY.get(first, parts[-1])


def role_group(role):
    r = str(role).lower()
    if any(k in r for k in ["cto", "technology", "engineering", "head of ai", "digital", "data"]): return "tech"
    if any(k in r for k in ["sales"]): return "sales"
    if any(k in r for k in ["marketing", "cmo", "retail media"]): return "marketing"
    if any(k in r for k in ["hr", "people", "hrbp"]): return "hr"
    if any(k in r for k in ["finance", "cfo"]): return "finance"
    return "other"


def build_features(data: pd.DataFrame) -> pd.DataFrame:
    d = pd.DataFrame()
    d["score"]          = data["score"]
    d["email_verified"] = data["email_verified"].astype(int)
    d["has_email"]      = (data["email"].notna() & (data["email"].astype(str).str.strip() != "")).astype(int)
    d["has_insights"]   = (data["insights"].notna() & (data["insights"].astype(str).str.strip() != "")).astype(int)
    d["segment"]        = data["segment"].fillna("unknown")
    d["email_source"]   = data["email_source"].fillna("none").replace("", "none")
    d["role_group"]     = data["role"].apply(role_group)
    d["country"]        = data["location"].apply(get_country)
    return d


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
            print(f"[ReplyScorer] model load failed (version mismatch?) — retrain locally: {e}")
    return _MODEL


def _norm_insights(v):
    if isinstance(v, dict):
        return json.dumps(v) if v else ""
    if isinstance(v, list):
        return json.dumps(v) if v else ""
    if v in (None, "", "{}", "null"):
        return ""
    return str(v)


def predict_scores(leads: list) -> dict:
    """Return {lead_id: reply_probability_percent} for a list of lead dicts."""
    model = _load_model()
    if not model or not leads:
        return {}
    rows = [{
        "score":          l.get("score") or 0,
        "email_verified": bool(l.get("email_verified")),
        "email":          l.get("email"),
        "insights":       _norm_insights(l.get("insights")),
        "segment":        l.get("segment") or "unknown",
        "email_source":   l.get("email_source"),
        "role":           l.get("role") or "",
        "location":       l.get("location") or "",
    } for l in leads]
    df = pd.DataFrame(rows)
    try:
        proba = model.predict_proba(build_features(df))[:, 1]
    except Exception as e:
        print(f"[ReplyScorer] prediction failed: {e}")
        return {}
    return {l["id"]: round(float(p) * 100, 1) for l, p in zip(leads, proba) if l.get("id")}
