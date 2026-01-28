# OCR Client

`tools/ocr_client.py` wraps Gemini OCR for document text extraction and analysis.

## Capabilities
- Extract raw text from PDF and image documents.
- Extract structured fields (policy number, dates, names).
- Answer questions about a document.
- Classify documents into categories.

## Configuration
- `GEMINI_API_KEY` (required)
- `GEMINI_OCR_MODEL` (optional, defaults to `gemini-2.5-flash`)

## Input Format
```json
{
  "mime_type": "application/pdf",
  "data": "base64_encoded_string"
}
```
