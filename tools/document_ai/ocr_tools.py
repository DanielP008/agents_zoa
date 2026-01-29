import os
import json
from typing import Dict, Any, Optional
from langchain_core.messages import HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.tools import tool

def _get_ocr_model() -> ChatGoogleGenerativeAI:
    """Return the configured Gemini model instance for OCR."""
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        raise ValueError("GEMINI_API_KEY environment variable not set")
    
    # Using gemini-1.5-flash as default for OCR tasks
    model_name = os.environ.get("GEMINI_OCR_MODEL", "gemini-1.5-flash")
    
    return ChatGoogleGenerativeAI(
        model=model_name,
        google_api_key=api_key,
        temperature=0.0
    )

def document_to_json(mime_type: str, b64_data: str, prompt_override: Optional[str] = None) -> Dict[str, Any]:
    """
    Core logic: Extracts all information from a document and returns it as a formatted JSON.
    Used programmatically by other Python tools and functions.
    """
    if not b64_data:
        return {"error": "No document data provided", "status": "failed"}

    llm = _get_ocr_model()
    
    default_prompt = (
        "Analyze this document and extract ALL relevant information into a well-structured JSON object. "
        "Include names, dates, numbers, addresses, and any other specific data points found. "
        "Use descriptive keys in English. If the document has multiple sections, reflect that in the JSON structure. "
        "Return ONLY the JSON object, no other text."
    )
    
    prompt = prompt_override or default_prompt
    
    message = HumanMessage(
        content=[
            {"type": "text", "text": prompt},
            {
                "type": "image_url",
                "image_url": f"data:{mime_type};base64,{b64_data}"
            }
        ]
    )

    try:
        response = llm.invoke([message])
        content = response.content.strip()
        
        # Clean up markdown code blocks if present
        if content.startswith("```json"):
            content = content[7:-3].strip()
        elif content.startswith("```"):
            content = content[3:-3].strip()
            
        return {
            "data": json.loads(content),
            "status": "success"
        }
    except json.JSONDecodeError as e:
        return {
            "error": f"Failed to parse OCR output as JSON: {str(e)}",
            "raw_output": response.content if 'response' in locals() else None,
            "status": "failed"
        }
    except Exception as e:
        return {
            "error": str(e),
            "status": "failed"
        }

@tool
def ocr_extract_json_tool(data: str) -> dict:
    """
    Agent interface: LangChain tool wrapper that allows AI agents to perform OCR via a JSON input string.
    Acts as a bridge between the agent's text output and the core document_to_json logic.
    """
    try:
        payload = json.loads(data)
        mime_type = payload.get("mime_type", "application/pdf")
        b64_data = payload.get("b64_data")
        prompt_hint = payload.get("prompt_hint")
        
        if not b64_data:
            return {"error": "b64_data is required"}
            
        return document_to_json(mime_type, b64_data, prompt_override=prompt_hint)
    except json.JSONDecodeError:
        return {"error": "Invalid JSON format in input"}
    except Exception as e:
        return {"error": str(e)}

@tool
def process_document(data: str) -> dict:
    """Convenience OCR tool that accepts JSON with mime_type and b64_data."""
    try:
        payload = json.loads(data)
        return document_to_json(payload.get("mime_type"), payload.get("b64_data"))
    except Exception:
        return {"error": "Invalid input format"}
