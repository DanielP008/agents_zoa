"""Pre-processing helpers for the orchestrator: attachments, NIF extraction."""
import base64
import os
import re
import logging

import requests

from core.db import SessionManager
from core.memory_schema import update_global
from services.zoa_client import (
    search_contact_by_phone,
    extract_nif_from_contact_search,
)

logger = logging.getLogger(__name__)
session_manager = SessionManager()


def _download_media_as_base64(url: str) -> str | None:
    """Download media from a URL and return its base64 representation."""
    try:
        headers = {}
        wa_token = os.environ.get("WHATSAPP_ACCESS_TOKEN")
        if wa_token:
            headers["Authorization"] = f"Bearer {wa_token}"
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        return base64.b64encode(resp.content).decode("utf-8")
    except Exception as e:
        logger.error(f"[ATTACHMENTS] Failed to download media from URL: {e}")
        return None


def extract_attachments(payload: dict) -> list:
    """Extract media attachments from the incoming payload.
    
    Supports:
    - media[].data / media[].base64  → inline base64
    - media[].url                    → downloaded and converted to base64
    - payload.image_base64           → legacy shorthand
    """
    attachments = []
    media = payload.get("media")
    if isinstance(media, dict):
        media = [media]
    if isinstance(media, list):
        for item in media:
            if not isinstance(item, dict):
                continue
            data = item.get("data") or item.get("base64")
            # If no inline data, try downloading from URL
            if not data:
                url = item.get("url")
                if url:
                    logger.info(f"[ATTACHMENTS] Downloading media from URL: {url[:80]}...")
                    data = _download_media_as_base64(url)
            if not data:
                continue
            attachments.append(
                {
                    "mime_type": item.get("mime_type") or item.get("type") or "application/octet-stream",
                    "data": data,
                    "filename": item.get("filename"),
                    "source": "media",
                }
            )
    image_b64 = payload.get("image_base64")
    if image_b64:
        attachments.append(
            {
                "mime_type": payload.get("image_mime_type") or "image/jpeg",
                "data": image_b64,
                "filename": payload.get("image_filename"),
                "source": "image_base64",
            }
        )
    return attachments


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
