import os
from langchain_google_genai import ChatGoogleGenerativeAI


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
        temperature=0.7,
        max_retries=2
    )
