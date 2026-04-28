import os
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq
from langchain_core.language_models import BaseChatModel


def _make_llm(provider: str, model_name: str, max_tokens: int = 8192) -> BaseChatModel:
    if provider == "gemini":
        return ChatGoogleGenerativeAI(
            model=model_name,
            google_api_key=os.getenv("GOOGLE_API_KEY"),
            temperature=0,
            max_output_tokens=max_tokens,
        )
    if provider == "groq":
        return ChatGroq(
            model=model_name,
            api_key=os.getenv("GROQ_API_KEY"),
            temperature=0,
            max_tokens=max_tokens,
        )
    raise ValueError(f"Unknown provider: {provider}")


def get_collector_llm() -> BaseChatModel:
    """Benchmark: llama=100, gpt-oss-120b=100. Using llama to avoid TPM clash with parser."""
    models = [
        ("groq",   "llama-3.3-70b-versatile"),
        ("groq",   "openai/gpt-oss-120b"),
        ("groq",   "openai/gpt-oss-20b"),
    ]
    llms = [_make_llm(p, m, max_tokens=8192) for p, m in models]
    primary, *fallbacks = llms
    return primary.with_fallbacks(fallbacks)


def get_qualifier_llm() -> BaseChatModel:
    """Benchmark winner: llama=87."""
    models = [
        ("groq",   "llama-3.3-70b-versatile"),
        ("groq",   "openai/gpt-oss-120b"),
        ("groq",   "openai/gpt-oss-20b"),
    ]
    llms = [_make_llm(p, m, max_tokens=16384) for p, m in models]
    primary, *fallbacks = llms
    return primary.with_fallbacks(fallbacks)


def get_enricher_llm() -> BaseChatModel:
    """Benchmark winner: gpt-oss-120b=100. Runs later so TPM is refreshed."""
    models = [
        ("groq",   "openai/gpt-oss-120b"),
        ("groq",   "llama-3.3-70b-versatile"),
        ("groq",   "openai/gpt-oss-20b"),
    ]
    llms = [_make_llm(p, m, max_tokens=4096) for p, m in models]
    primary, *fallbacks = llms
    return primary.with_fallbacks(fallbacks)


def get_writer_llm() -> BaseChatModel:
    """Benchmark winner: llama=100. Many concurrent calls need high TPM."""
    models = [
        ("groq",   "llama-3.3-70b-versatile"),
        ("groq",   "openai/gpt-oss-120b"),
        ("groq",   "openai/gpt-oss-20b"),
    ]
    llms = [_make_llm(p, m, max_tokens=4096) for p, m in models]
    primary, *fallbacks = llms
    return primary.with_fallbacks(fallbacks)