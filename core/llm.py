import os
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI

def get_llm(model_name: str = None):
    """
    Get a configured LLM instance.
    
    Args:
        model_name: Optional model name override. Defaults to GEMINI_MODEL env var
                   or 'gemini-3-flash-preview'.
    
    Returns:
        ChatGoogleGenerativeAI instance
    """
    api_key = os.environ.get("GEMINI_API_KEY", "")
    model = model_name or os.environ.get("GEMINI_MODEL", "gemini-3-flash-preview")
    
    return ChatGoogleGenerativeAI(
        model=model, 
        google_api_key=api_key,
        temperature=0.1,
        max_retries=2,
        timeout=30.0
    )

def _get_openai_fast(model_name: str = None):
    """Get a fast OpenAI instance."""
    api_key = os.environ.get("OPENAI_API_KEY", "")
    model = model_name or os.environ.get("OPENAI_MODEL_FAST", "gpt-5.2")
    return ChatOpenAI(
        model=model,
        api_key=api_key,
        temperature=0.1,
        max_retries=2
    )

def _get_gemini_fast(model_name: str = None):
    """Get a fast Gemini instance."""
    api_key = os.environ.get("GEMINI_API_KEY", "")
    model = model_name or os.environ.get("GEMINI_MODEL_FAST", "gemini-2.5-flash")
    return ChatGoogleGenerativeAI(
        model=model,
        google_api_key=api_key,
        temperature=0.1,
        max_retries=2,
        max_output_tokens=512,
        timeout=15.0
    )

def get_llm_fast(model_name: str = None):
    """
    Get a fast LLM instance for classifiers.
    Dispatches to either OpenAI or Gemini based on FAST_LLM_PROVIDER.
    """
    provider = os.environ.get("FAST_LLM_PROVIDER", "openai").lower()
    
    if provider == "openai":
        return _get_openai_fast(model_name)
    
    return _get_gemini_fast(model_name)
