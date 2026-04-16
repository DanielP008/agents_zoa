"""Pre-processing helpers for the orchestrator: attachments, NIF extraction, OCR."""

import base64
import json
import logging
import re

import requests

from core.memory import update_global
from services.ocr_service import extract_document_data
from services.zoa_client import (
    search_contact_by_phone,
    extract_nif_from_contact_search,
    download_media,
)

logger = logging.getLogger(__name__)


def extract_attachments(payload: dict) -> list:
    """Extract media attachments from the incoming payload.
    
    Supports:
    - type "image"/"document" → downloads base64 via ZOA using wamid
    - media[].data / media[].base64 → inline base64 (legacy/tests)
    - payload.image_base64 → legacy shorthand
    """
    attachments = []
    company_id = payload.get("phone_number_id") or payload.get("company_id") or "default"
    msg_type = payload.get("type")

    # Handle image/document from WhatsApp (real payloads)
    if msg_type in ("image", "document"):
        media_obj = payload.get(msg_type, {})
        mime_type = media_obj.get("mime_type", "application/octet-stream")
        message_ids = payload.get("message_ids", [])
        wamid = message_ids[0] if message_ids else payload.get("id")
        media_id = media_obj.get("id")
        if wamid or media_id:
            logger.info(f"[ATTACHMENTS] Downloading {msg_type} via ZOA, wamid={wamid}, media_id={media_id}")
            result = download_media(wamid, company_id, media_id=media_id)
            data = result.get("data") or result.get("base64")

            if not data and result.get("media_url"):
                data = _download_from_url(result["media_url"])
                if not mime_type or mime_type == "application/octet-stream":
                    mime_type = result.get("mime_type") or mime_type

            if data:
                attachments.append({
                    "mime_type": mime_type,
                    "data": data,
                    "filename": media_obj.get("filename") or result.get("file_name"),
                    "source": msg_type,
                })
            else:
                logger.error(f"[ATTACHMENTS] ZOA returned no usable data: {result}")
        else:
            logger.error("[ATTACHMENTS] No wamid or media_id found to download media")
        return attachments

    # Legacy: media[] with inline base64 (tests / old format)
    media = payload.get("media")
    if isinstance(media, dict):
        media = [media]
    if isinstance(media, list):
        for item in media:
            if not isinstance(item, dict):
                continue
            data = item.get("data") or item.get("base64")
            if not data:
                continue
            attachments.append({
                "mime_type": item.get("mime_type") or item.get("type") or "application/octet-stream",
                "data": data,
                "filename": item.get("filename"),
                "source": "media",
            })

    # Legacy: image_base64 shorthand
    image_b64 = payload.get("image_base64")
    if image_b64:
        attachments.append({
            "mime_type": payload.get("image_mime_type") or "image/jpeg",
            "data": image_b64,
            "filename": payload.get("image_filename"),
            "source": "image_base64",
        })
    return attachments


def process_attachments_ocr(memory: dict) -> tuple[dict, str]:
    """Run OCR on all unprocessed attachments and return extracted text.

    Returns:
        (updated_memory, ocr_context_text)
    """
    global_mem = memory.get("global", {})
    attachments = global_mem.get("attachments", [])
    if not attachments:
        return memory, ""

    processed = set(global_mem.get("processed_attachment_indices", []))
    ocr_texts = []

    for i, att in enumerate(attachments):
        if i in processed:
            continue
        if not isinstance(att, dict):
            continue
        b64_data = att.get("data")
        if not b64_data:
            continue

        mime_type = att.get("mime_type", "application/octet-stream")
        filename = att.get("filename", f"adjunto_{i+1}")

        logger.info(f"[OCR] Processing attachment {i}: {filename} ({mime_type})")
        result = extract_document_data(mime_type, b64_data)

        if result.get("status") == "success":
            extracted = result.get("data", {})
            ocr_texts.append(
                f"[Contenido extraído de '{filename}' ({mime_type})]:\n"
                f"{json.dumps(extracted, ensure_ascii=False, indent=2)}"
            )
            att["ocr_status"] = "success"
            att["ocr_extracted"] = extracted
            logger.info(f"[OCR] OCR success for {filename}")

            # Extract client name from OCR data and store in global memory
            if isinstance(extracted, dict) and not global_mem.get("client_name"):
                _extract_client_name_from_ocr(extracted, global_mem)
        else:
            raw = result.get("raw_output")
            if raw:
                ocr_texts.append(
                    f"[Contenido extraído de '{filename}' ({mime_type})]:\n{raw}"
                )
                att["ocr_status"] = "raw"
            else:
                att["ocr_status"] = "failed"
                att["ocr_error"] = result.get("error", "OCR failed")
                logger.error(f"[OCR] OCR failed for {filename}: {result.get('error')}")

        # Prune base64 after processing
        att.pop("data", None)
        att["data_pruned"] = True
        processed.add(i)

    if processed:
        global_mem["processed_attachment_indices"] = sorted(processed)
        global_mem["attachments"] = attachments
        memory["global"] = global_mem

    return memory, "\n\n".join(ocr_texts)


def is_valid_nif(nif: str) -> bool:
    """Check if the provided NIF/DNI/NIE/CIF matches a valid Spanish format.
    
    Standard patterns:
    - DNI: 8 digits + 1 letter (e.g. 12345678A)
    - NIE: 1 letter (XYZ) + 7 digits + 1 letter (e.g. X1234567L)
    - CIF/Other: 1 letter + 7 digits + 1 letter/digit (e.g. B12345678)
    """
    if not nif:
        return False
    
    # Remove any spaces or dashes
    nif = nif.replace(" ", "").replace("-", "").upper()
    
    patterns = [
        r"^\d{8}[A-Z]$",        # DNI
        r"^[XYZ]\d{7}[A-Z]$",   # NIE
        r"^[A-Z]\d{7}[A-Z0-9]$" # CIF / Others
    ]
    
    for pattern in patterns:
        if re.match(pattern, nif):
            return True
    return False


def extract_nif_from_text(text: str) -> str:
    """Extract NIF/DNI/NIE/CIF from free text using regex."""
    if not text:
        return ""
    # We use the same patterns as is_valid_nif but with word boundaries for extraction
    patterns = [
        r"\b\d{8}[A-Za-z]\b",
        r"\b[XYZ]\d{7}[A-Za-z]\b",
        r"\b[A-Za-z]\d{7}[A-Za-z0-9]\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            val = match.group(0).upper()
            if is_valid_nif(val):
                return val
    return ""


def try_silent_nif_lookup(memory: dict, wa_id: str, company_id: str) -> tuple[dict, str]:
    """
    Silent CRM lookup for NIF. No user interaction.
    Only runs once per session (skips if NIF already known or lookup already attempted).
    
    Returns:
        tuple: (updated_memory, nif_value)
    """
    global_mem = memory.get("global", {})
    nif_value = global_mem.get("nif")
    nif_lookup_done = global_mem.get("nif_lookup_done", False)

    if nif_value or nif_lookup_done:
        return memory, nif_value or ""

    # Try CRM/ZOA lookup
    if wa_id and company_id:
        logger.info(f"[NIF_LOOKUP] Silent CRM lookup for wa_id={wa_id}")
        try:
            contact_response = search_contact_by_phone(wa_id, company_id)
            nif_value = extract_nif_from_contact_search(contact_response)
            if nif_value:
                logger.info(f"[NIF_LOOKUP] Found NIF from CRM: {nif_value}")
        except Exception as e:
            logger.error(f"[NIF_LOOKUP] CRM error: {e}")

    # Save result
    if nif_value:
        memory = update_global(memory, nif=nif_value, nif_lookup_done=True)
    else:
        memory = update_global(memory, nif_lookup_done=True)

    return memory, nif_value or ""


def _extract_client_name_from_ocr(extracted: dict, global_mem: dict) -> None:
    """Extract client full name from OCR-extracted document data and store in global_mem."""

    # Check for a single-field full name first
    for key in ("nombre_completo", "titular", "full_name"):
        val = extracted.get(key)
        if val and isinstance(val, str) and val.strip():
            global_mem["client_name"] = val.strip()
            logger.info(f"[OCR] Extracted client name from document ({key}): {val.strip()}")
            return

    # Build from nombre + apellidos (handles Spanish DNI format)
    nombre = ""
    for key in ("nombre", "name"):
        val = extracted.get(key)
        if val and isinstance(val, str) and val.strip():
            nombre = val.strip()
            break

    apellidos_parts = []
    for key in ("apellidos", "apellido"):
        val = extracted.get(key)
        if val and isinstance(val, str) and val.strip():
            apellidos_parts.append(val.strip())
            break

    if not apellidos_parts:
        p1 = (extracted.get("primer_apellido") or "").strip()
        p2 = (extracted.get("segundo_apellido") or "").strip()
        if p1:
            apellidos_parts.append(p1)
        if p2:
            apellidos_parts.append(p2)

    apellidos = " ".join(apellidos_parts)

    if nombre and apellidos:
        full_name = f"{nombre} {apellidos}"
    elif nombre:
        full_name = nombre
    elif apellidos:
        full_name = apellidos
    else:
        return

    # Normalize to title case (OCR often returns UPPERCASE from DNI)
    full_name = full_name.title()
    global_mem["client_name"] = full_name
    logger.info(f"[OCR] Extracted client name from document: {full_name}")


def try_extract_client_name_retroactive(memory: dict) -> dict:
    """Retroactive extraction: if client_name is missing, try to recover it
    from already-processed OCR data stored in attachments or from conversation history."""
    global_mem = memory.get("global", {})
    if global_mem.get("client_name"):
        return memory

    # Strategy 1: Check ocr_extracted stored in attachment objects
    attachments = global_mem.get("attachments", [])
    for att in attachments:
        if not isinstance(att, dict):
            continue
        extracted = att.get("ocr_extracted")
        if isinstance(extracted, dict):
            _extract_client_name_from_ocr(extracted, global_mem)
            if global_mem.get("client_name"):
                logger.info(f"[RETROACTIVE] Recovered client_name from stored OCR data: {global_mem['client_name']}")
                memory["global"] = global_mem
                return memory

    # Strategy 2: Parse OCR JSON blocks from conversation history
    history = memory.get("conversation_history", [])
    for turn in reversed(history):
        text = turn.get("text", "") if isinstance(turn, dict) else ""
        if "[Contenido extraído de" not in text:
            continue
        json_blocks = re.findall(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', text)
        for block in json_blocks:
            try:
                parsed = json.loads(block)
                if isinstance(parsed, dict):
                    _extract_client_name_from_ocr(parsed, global_mem)
                    if global_mem.get("client_name"):
                        logger.info(f"[RETROACTIVE] Recovered client_name from history: {global_mem['client_name']}")
                        memory["global"] = global_mem
                        return memory
            except (json.JSONDecodeError, ValueError):
                continue

    return memory


def _download_from_url(url: str, timeout: int = 20) -> str | None:
    """Download binary from a URL and return base64-encoded string."""
    try:
        logger.info(f"[ATTACHMENTS] Downloading binary from media_url: {url[:120]}...")
        resp = requests.get(url, timeout=timeout)
        if resp.status_code == 200 and resp.content:
            b64 = base64.b64encode(resp.content).decode("utf-8")
            logger.info(f"[ATTACHMENTS] Downloaded {len(resp.content)} bytes from media_url")
            return b64
        logger.error(f"[ATTACHMENTS] media_url returned HTTP {resp.status_code}")
    except Exception as e:
        logger.error(f"[ATTACHMENTS] Failed to download from media_url: {e}")
    return None
