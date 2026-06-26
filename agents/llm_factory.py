"""
llm_factory.py — Build LLMs with automatic key rotation and provider fallbacks.

Priority order when a rate-limit is hit:
  1. All Groq keys (GROQ_API_KEY, GROQ_API_KEY1 … GROQ_API_KEY5) × preferred model
  2. Same key pool × fallback models
  3. Google Gemini keys (GOOGLE_API_KEY, GOOGLE_API_KEY1 …)
  4. Together AI  (TOGETHER_API_KEY)
  5. OpenRouter   (OPENROUTER_API_KEY)
"""

import os
from langchain_groq import ChatGroq
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.language_models import BaseChatModel
from dotenv import load_dotenv

load_dotenv()


# ── Key collectors ────────────────────────────────────────────────────────────

def _groq_keys() -> list[str]:
    """Return all GROQ_API_KEY / GROQ_API_KEY1…N values that are set."""
    keys = []
    for suffix in ["", "1", "2", "3", "4", "5"]:
        k = os.getenv(f"GROQ_API_KEY{suffix}", "").strip()
        if k and k not in keys:
            keys.append(k)
    return keys


def _google_keys() -> list[str]:
    keys = []
    for suffix in ["", "1", "2", "3"]:
        k = os.getenv(f"GOOGLE_API_KEY{suffix}", "").strip()
        if k and k not in keys:
            keys.append(k)
    return keys


# ── Individual LLM builders ───────────────────────────────────────────────────

def _groq(model: str, api_key: str, max_tokens: int) -> BaseChatModel:
    return ChatGroq(model=model, api_key=api_key, temperature=0, max_tokens=max_tokens)


def _gemini(model: str, api_key: str, max_tokens: int) -> BaseChatModel:
    return ChatGoogleGenerativeAI(
        model=model, google_api_key=api_key,
        temperature=0, max_output_tokens=max_tokens,
    )


def _together(model: str, max_tokens: int) -> BaseChatModel | None:
    """Together AI via OpenAI-compatible endpoint."""
    key = os.getenv("TOGETHER_API_KEY", "").strip()
    if not key:
        return None
    try:
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=model, api_key=key,
            base_url="https://api.together.xyz/v1",
            temperature=0, max_tokens=max_tokens,
        )
    except ImportError:
        return None


def _openrouter(model: str, max_tokens: int) -> BaseChatModel | None:
    key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not key:
        return None
    try:
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=model, api_key=key,
            base_url="https://openrouter.ai/api/v1",
            temperature=0, max_tokens=max_tokens,
        )
    except ImportError:
        return None


# ── Fallback chain builder ────────────────────────────────────────────────────

def _build_chain(
    groq_models: list[str],
    gemini_model: str,
    together_model: str,
    openrouter_model: str,
    max_tokens: int,
) -> BaseChatModel:
    """
    Build: [primary_groq_model × all_keys] → [fallback_groq_models × all_keys]
           → [gemini × all_google_keys] → together → openrouter
    """
    llms: list[BaseChatModel] = []

    groq_keys  = _groq_keys()
    google_keys = _google_keys()

    # Groq: each model × each key — iterate models first so we exhaust all keys
    # for the best model before moving to a weaker one
    for model in groq_models:
        for key in groq_keys:
            llms.append(_groq(model, key, max_tokens))

    # Google Gemini fallback
    for key in google_keys:
        llms.append(_gemini(gemini_model, key, max_tokens))

    # Together AI fallback
    t = _together(together_model, max_tokens)
    if t:
        llms.append(t)

    # OpenRouter fallback
    r = _openrouter(openrouter_model, max_tokens)
    if r:
        llms.append(r)

    if not llms:
        raise RuntimeError("No LLM credentials found. Check your .env file.")

    primary, *fallbacks = llms
    return primary.with_fallbacks(fallbacks) if fallbacks else primary


# ── Public getters ────────────────────────────────────────────────────────────

def get_collector_llm() -> BaseChatModel:
    return _build_chain(
        groq_models    = ["llama-3.3-70b-versatile", "openai/gpt-oss-120b", "openai/gpt-oss-20b"],
        gemini_model   = "gemini-1.5-flash",
        together_model = "meta-llama/Llama-3.3-70B-Instruct-Turbo",
        openrouter_model = "meta-llama/llama-3.3-70b-instruct",
        max_tokens     = 8192,
    )


def get_qualifier_llm() -> BaseChatModel:
    return _build_chain(
        groq_models    = ["llama-3.3-70b-versatile", "openai/gpt-oss-120b", "openai/gpt-oss-20b"],
        gemini_model   = "gemini-1.5-flash",
        together_model = "meta-llama/Llama-3.3-70B-Instruct-Turbo",
        openrouter_model = "meta-llama/llama-3.3-70b-instruct",
        max_tokens     = 16384,
    )


def get_enricher_llm() -> BaseChatModel:
    return _build_chain(
        groq_models    = ["openai/gpt-oss-120b", "llama-3.3-70b-versatile", "openai/gpt-oss-20b"],
        gemini_model   = "gemini-1.5-pro",
        together_model = "meta-llama/Llama-3.3-70B-Instruct-Turbo",
        openrouter_model = "openai/gpt-4o-mini",
        max_tokens     = 4096,
    )


def get_writer_llm() -> BaseChatModel:
    return _build_chain(
        groq_models    = ["llama-3.3-70b-versatile", "openai/gpt-oss-120b", "openai/gpt-oss-20b"],
        gemini_model   = "gemini-1.5-flash",
        together_model = "meta-llama/Llama-3.3-70B-Instruct-Turbo",
        openrouter_model = "meta-llama/llama-3.3-70b-instruct",
        max_tokens     = 4096,
    )


def get_analyst_llm() -> BaseChatModel:
    """LLM used by the Analyst agent to write optimization recommendations."""
    return _build_chain(
        groq_models    = ["openai/gpt-oss-120b", "llama-3.3-70b-versatile", "openai/gpt-oss-20b"],
        gemini_model   = "gemini-1.5-pro",
        together_model = "meta-llama/Llama-3.3-70B-Instruct-Turbo",
        openrouter_model = "openai/gpt-4o-mini",
        max_tokens     = 2048,
    )
