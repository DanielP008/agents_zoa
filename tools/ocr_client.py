import base64
import os

from langchain_core.messages import HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI


def extract_text(document: dict) -> dict:
    """
    Extracts text from a document (PDF/Image) using Gemini 1.5 Flash.
    Expected 'document' dict format:
    {
        "mime_type": "application/pdf" | "image/jpeg" | ...,
        "data": "base64_encoded_string"
    }
    """
    api_key = os.environ.get("GEMINI_API_KEY", "")
    ocr_model = os.environ.get("GEMINI_OCR_MODEL", "gemini-1.5-flash")
    # Flash is efficient for multimodal tasks like OCR
    llm = ChatGoogleGenerativeAI(
        model=ocr_model, 
        google_api_key=api_key,
        temperature=0.0
    )

    mime_type = document.get("mime_type", "application/pdf")
    b64_data = document.get("data", "")

    if not b64_data:
        return {"error": "No document data provided"}

    message = HumanMessage(
        content=[
            {
                "type": "text",
                "text": "Please transcribe the full text from this document explicitly. Return only the text."
            },
            {
                "type": "image_url",
                "image_url": f"data:{mime_type};base64,{b64_data}"
            }
        ]
    )

    try:
        response = llm.invoke([message])
        return {
            "text": response.content,
            "confidence": 1.0, # Gemini doesn't return confidence score by default
            "status": "success"
        }
    except Exception as e:
        return {
            "text": "",
            "error": str(e),
            "status": "failed"
        }
