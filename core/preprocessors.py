"""Pre-processing helpers for the orchestrator: attachments, NIF extraction, OCR."""

import json
import logging
import re

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
        if wamid:
            logger.info(f"[ATTACHMENTS] Downloading {msg_type} via ZOA, wamid={wamid}")
            result = download_media(wamid, company_id)
            data = result.get("data") or result.get("base64")
            if data:
                attachments.append({
                    "mime_type": mime_type,
                    "data": data,
                    "filename": media_obj.get("filename"),
                    "source": msg_type,
                })
            else:
                logger.error(f"[ATTACHMENTS] ZOA returned no data: {result}")
        else:
            logger.error("[ATTACHMENTS] No wamid found to download media")
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
            logger.info(f"[OCR] OCR success for {filename}")
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


def extract_nif_from_text(text: str) -> str:
    """Extract NIF/DNI/NIE/CIF from free text using regex."""
    if not text:
        return ""
    patterns = [
        r"\b\d{8}[A-Za-z]\b",
        r"\b[XYZ]\d{7}[A-Za-z]\b",
        r"\b[A-Za-z]\d{7}[A-Za-z0-9]\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(0).upper()
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
