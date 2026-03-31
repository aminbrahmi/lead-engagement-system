# agents/llm_factory.py
import os
from langchain_groq import ChatGroq
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.language_models import BaseChatModel


def _make_llm(provider: str, model_name: str) -> BaseChatModel:
    if provider == "groq":
        return ChatGroq(
            model=model_name,
            api_key=os.getenv("GROQ_API_KEY"),
            temperature=0,
        )
    if provider == "gemini":
        return ChatGoogleGenerativeAI(
            model=model_name,
            google_api_key=os.getenv("GOOGLE_API_KEY"),
            temperature=0,
        )
    raise ValueError(f"Unknown provider: {provider}")


# Mirrors the old MODELS list in collector.py
_COLLECTOR_MODELS = [
    ("groq",   "openai/gpt-oss-20b"),
    ("gemini", "gemini-2.5-flash"),
    ("groq",   "openai/gpt-oss-120b"),
    ("groq",   "llama-3.3-70b-versatile"),
]


def get_collector_llm() -> BaseChatModel:
    """Primary LLM with automatic fallback chain — replaces the manual retry loop."""
    llms = [_make_llm(p, m) for p, m in _COLLECTOR_MODELS]
    primary, *fallbacks = llms
    return primary.with_fallbacks(fallbacks)


def get_qualifier_llm() -> BaseChatModel:
    """Qualifier LLM — honours QUALIFIER_MODEL env var, falls back to primary."""
    raw = os.getenv("QUALIFIER_MODEL", "groq/openai/gpt-oss-20b")
    # env var format: "groq/model-name" or "gemini/model-name"
    provider, _, model_name = raw.partition("/")
    primary = _make_llm(provider, model_name)
    fallbacks = [_make_llm(p, m) for p, m in _COLLECTOR_MODELS[1:]]
    return primary.with_fallbacks(fallbacks)