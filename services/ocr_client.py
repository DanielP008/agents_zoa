"""
OCR Client using Google Gemini 2.5 Flash for document text extraction.
Supports PDFs, images, and structured data extraction from documents.
"""

import base64
import os
from typing import Dict, Any, Optional, List
from pathlib import Path

from langchain_core.messages import HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI


def _get_ocr_model() -> ChatGoogleGenerativeAI:
    """Return the configured Gemini OCR model instance."""
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        raise ValueError("GEMINI_API_KEY environment variable not set")
    
    model_name = os.environ.get("GEMINI_OCR_MODEL", "gemini-2.5-flash")
    
    return ChatGoogleGenerativeAI(
        model=model_name,
        google_api_key=api_key,
        temperature=0.0
    )


def extract_text(document: Dict[str, str]) -> Dict[str, Any]:
    """Extract raw text from a document using Gemini OCR."""
    try:
        mime_type = document.get("mime_type", "application/pdf")
        b64_data = document.get("data", "")

        if not b64_data:
            return {
                "text": "",
                "status": "failed",
                "error": "No document data provided"
            }

        llm = _get_ocr_model()
        
        message = HumanMessage(
            content=[
                {
                    "type": "text",
                    "text": (
                        "Extract and transcribe ALL text from this document. "
                        "Preserve the original structure and formatting as much as possible. "
                        "Return only the extracted text without any additional commentary."
                    )
                },
                {
                    "type": "image_url",
                    "image_url": f"data:{mime_type};base64,{b64_data}"
                }
            ]
        )

        response = llm.invoke([message])
        
        return {
            "text": response.content.strip(),
            "status": "success"
        }
        
    except Exception as e:
        return {
            "text": "",
            "status": "failed",
            "error": str(e)
        }


def extract_structured_data(
    document: Dict[str, str],
    fields: List[str],
    instructions: Optional[str] = None
) -> Dict[str, Any]:
    """Extract selected fields from a document."""
    try:
        mime_type = document.get("mime_type", "application/pdf")
        b64_data = document.get("data", "")

        if not b64_data:
            return {
                "data": {},
                "status": "failed",
                "error": "No document data provided"
            }

        llm = _get_ocr_model()
        
        fields_str = ", ".join(fields)
        prompt = (
            f"Extract the following specific information from this document: {fields_str}\n\n"
            "Return the data in a structured format like this:\n"
            "field_name: value\n"
            "another_field: value\n\n"
            "If a field is not found in the document, write: field_name: NOT_FOUND\n"
        )
        
        if instructions:
            prompt += f"\nContext: {instructions}\n"
        
        message = HumanMessage(
            content=[
                {
                    "type": "text",
                    "text": prompt
                },
                {
                    "type": "image_url",
                    "image_url": f"data:{mime_type};base64,{b64_data}"
                }
            ]
        )

        response = llm.invoke([message])
        
        extracted_data = {}
        for line in response.content.strip().split("\n"):
            if ":" in line:
                key, value = line.split(":", 1)
                key = key.strip()
                value = value.strip()
                if value.upper() != "NOT_FOUND":
                    extracted_data[key] = value
        
        return {
            "data": extracted_data,
            "status": "success"
        }
        
    except Exception as e:
        return {
            "data": {},
            "status": "failed",
            "error": str(e)
        }


def analyze_document(
    document: Dict[str, str],
    question: str
) -> Dict[str, Any]:
    """Answer a question about the document content."""
    try:
        mime_type = document.get("mime_type", "application/pdf")
        b64_data = document.get("data", "")

        if not b64_data:
            return {
                "answer": "",
                "status": "failed",
                "error": "No document data provided"
            }

        llm = _get_ocr_model()
        
        message = HumanMessage(
            content=[
                {
                    "type": "text",
                    "text": f"Based on this document, answer the following question:\n\n{question}\n\nProvide a clear, concise answer."
                },
                {
                    "type": "image_url",
                    "image_url": f"data:{mime_type};base64,{b64_data}"
                }
            ]
        )

        response = llm.invoke([message])
        
        return {
            "answer": response.content.strip(),
            "status": "success"
        }
        
    except Exception as e:
        return {
            "answer": "",
            "status": "failed",
            "error": str(e)
        }


def extract_text_from_file(file_path: str) -> Dict[str, Any]:
    """Extract text from a local PDF or image file."""
    try:
        path = Path(file_path)
        
        if not path.exists():
            return {
                "text": "",
                "status": "failed",
                "error": f"File not found: {file_path}"
            }
        
        extension = path.suffix.lower()
        mime_types = {
            ".pdf": "application/pdf",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".gif": "image/gif",
            ".webp": "image/webp",
            ".bmp": "image/bmp",
            ".tiff": "image/tiff",
            ".tif": "image/tiff"
        }
        
        mime_type = mime_types.get(extension)
        if not mime_type:
            return {
                "text": "",
                "status": "failed",
                "error": f"Unsupported file type: {extension}"
            }
        
        with open(file_path, "rb") as f:
            file_data = f.read()
            b64_data = base64.b64encode(file_data).decode("utf-8")
        
        document = {
            "mime_type": mime_type,
            "data": b64_data
        }
        
        return extract_text(document)
        
    except Exception as e:
        return {
            "text": "",
            "status": "failed",
            "error": str(e)
        }

def classify_document(
    document: Dict[str, str],
    categories: List[str]
) -> Dict[str, Any]:
    """Classify a document into one of the given categories."""
    try:
        mime_type = document.get("mime_type", "application/pdf")
        b64_data = document.get("data", "")

        if not b64_data:
            return {
                "category": "",
                "confidence": "low",
                "reasoning": "",
                "status": "failed",
                "error": "No document data provided"
            }

        llm = _get_ocr_model()
        
        categories_str = ", ".join(categories)
        prompt = (
            f"Analyze this document and classify it into ONE of these categories: {categories_str}\n\n"
            "Respond in the following format:\n"
            "Category: [chosen_category]\n"
            "Confidence: [high/medium/low]\n"
            "Reasoning: [brief explanation]\n"
        )
        
        message = HumanMessage(
            content=[
                {
                    "type": "text",
                    "text": prompt
                },
                {
                    "type": "image_url",
                    "image_url": f"data:{mime_type};base64,{b64_data}"
                }
            ]
        )

        response = llm.invoke([message])
        
        result = {
            "category": "",
            "confidence": "medium",
            "reasoning": "",
            "status": "success"
        }
        
        for line in response.content.strip().split("\n"):
            if ":" in line:
                key, value = line.split(":", 1)
                key = key.strip().lower()
                value = value.strip()
                
                if key == "category":
                    result["category"] = value
                elif key == "confidence":
                    result["confidence"] = value.lower()
                elif key == "reasoning":
                    result["reasoning"] = value
        
        return result
        
    except Exception as e:
        return {
            "category": "",
            "confidence": "low",
            "reasoning": "",
            "status": "failed",
            "error": str(e)
        }
