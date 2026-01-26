import os
from langchain_google_genai import ChatGoogleGenerativeAI

def get_llm():
    api_key = os.environ.get("GEMINI_API_KEY", "")
    model = os.environ.get("GEMINI_MODEL", "gemini-1.5-flash")
    # Enable strict mode for better structured output reliability
    return ChatGoogleGenerativeAI(
        model=model, 
        google_api_key=api_key,
        temperature=0.7,
        max_retries=2
    )
