"""LLM factory: creates configured LLM instances for agents and classifiers."""

import os

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_mistralai import ChatMistralAI
from langchain_openai import ChatOpenAI


def get_llm(model_name: str = None):
    """Get a configured LLM instance. Dispatches based on LLM_PROVIDER."""
    provider = os.environ.get("LLM_PROVIDER", "mistral").lower()

    if provider == "mistral":
        api_key = os.environ.get("MISTRAL_API_KEY", "")
        model = model_name or os.environ.get("MISTRAL_MODEL", "mistral-large-latest")
        return ChatMistralAI(
            model=model,
            mistral_api_key=api_key,
            temperature=0.1,
            max_retries=2,
            timeout=300.0,
        )

    # Default to Gemini
    api_key = os.environ.get("GEMINI_API_KEY", "")
    model = model_name or os.environ.get("GEMINI_MODEL", "gemini-3-flash-preview")

    return ChatGoogleGenerativeAI(
        model=model,
        google_api_key=api_key,
        temperature=0.1,
        max_retries=2,
        timeout=300.0,
    )


def get_llm_fast(model_name: str = None):
    """Get a fast LLM instance for classifiers. Dispatches based on FAST_LLM_PROVIDER."""
    provider = os.environ.get("FAST_LLM_PROVIDER", "openai").lower()

    if provider == "openai":
        return ChatOpenAI(
            model=model_name or os.environ.get("OPENAI_MODEL_FAST", "gpt-5.2"),
            api_key=os.environ.get("OPENAI_API_KEY", ""),
            temperature=0.1,
            max_retries=2,
        )

    return ChatGoogleGenerativeAI(
        model=model_name or os.environ.get("GEMINI_MODEL_FAST", "gemini-2.5-flash"),
        google_api_key=os.environ.get("GEMINI_API_KEY", ""),
        temperature=0.1,
        max_retries=2,
        max_output_tokens=512,
        timeout=15.0,
    )
