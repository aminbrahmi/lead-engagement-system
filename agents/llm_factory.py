import os
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq
from langchain_core.language_models import BaseChatModel


def _make_llm(provider: str, model_name: str) -> BaseChatModel:
    if provider == "gemini":
        return ChatGoogleGenerativeAI(
            model=model_name,
            google_api_key=os.getenv("GOOGLE_API_KEY"),
            temperature=0,
        )
    if provider == "groq":
        return ChatGroq(
            model=model_name,
            api_key=os.getenv("GROQ_API_KEY"),
            temperature=0,
        )
    raise ValueError(f"Unknown provider: {provider}")


# Order matters — primary first, weakest last
# gpt-oss-120b : best quality, slower  → primary for scoring/enrichment
# gemini-2.5-flash : best quality, needs GOOGLE_API_KEY → second
# llama-3.3-70b : fast, reliable JSON → workhorse fallback
# gpt-oss-20b : fast but weaker quality → last resort only
_MODELS = [
    ("groq",   "openai/gpt-oss-120b"),       # primary — best reasoning
    ("gemini", "gemini-2.5-flash"),           # second  — best quality overall
    ("groq",   "llama-3.3-70b-versatile"),   # fallback — fast + reliable
    ("groq",   "openai/gpt-oss-20b"),        # last resort — weakest
]


def get_collector_llm() -> BaseChatModel:
    llms = [_make_llm(p, m) for p, m in _MODELS]
    primary, *fallbacks = llms
    return primary.with_fallbacks(fallbacks)


def get_qualifier_llm() -> BaseChatModel:
    return get_collector_llm()


def get_writer_llm() -> BaseChatModel:
    """
    Best model for cold email generation based on benchmark results.
    llama-3.3-70b-versatile scores highest on specificity, no-filler,
    CTA quality and subject line — fast + reliable JSON output.
    Falls back to gpt-oss-120b if rate-limited.
    """
    _WRITER_MODELS = [
        ("groq",   "llama-3.3-70b-versatile"),  # winner — benchmark score 80%
        ("groq",   "openai/gpt-oss-120b"),       # fallback
        ("gemini", "gemini-2.5-flash"),           # fallback if GOOGLE_API_KEY set
    ]
    llms = [_make_llm(p, m) for p, m in _WRITER_MODELS]
    primary, *fallbacks = llms
    return primary.with_fallbacks(fallbacks)