# OCR Tools

`tools/ocr_tools.py` uses Google Gemini to extract data from documents (PDFs, images) and return it as a structured JSON object.

## Capabilities
- **Generalistic Extraction**: Captures all relevant data points (names, dates, numbers, addresses) without requiring a specific schema.
- **JSON Output**: Returns a clean JSON object for easy consumption by agents and other tools.
- **Format Handling**: Automatically handles markdown code blocks and other LLM formatting artifacts.

## Key Functions
- `document_to_json(mime_type, b64_data, prompt_override=None)`: The core function that performs the OCR and JSON extraction.
- `ocr_extract_json_tool`: The LangChain tool wrapper for agents.

## Usage in Other Tools
- `tools/policy_tools.py`: Uses OCR to process insurance policies.
- `tools/consult_policy_tools.py`: Uses OCR for document-based policy inquiries.

## Configuration
- `GEMINI_API_KEY`: Required for Gemini access.
- `GEMINI_OCR_MODEL`: Optional, defaults to `gemini-1.5-flash`.
