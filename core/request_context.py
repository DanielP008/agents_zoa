"""Channel-agnostic request context and wait-message callback."""

import contextvars
import logging
from typing import Any, Dict

from langchain_core.callbacks import BaseCallbackHandler

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# "Please wait" message — sent once per request on first qualifying tool call
# ---------------------------------------------------------------------------
_WAIT_MESSAGE = (
    "Vale, voy a revisar tu ficha de cliente. "
    "Por favor espera unos segundos y te contesto enseguida."
)
_EXCLUDED_TOOLS = frozenset({
    "end_chat_tool",
    "redirect_to_receptionist_tool",
    "send_whatsapp_tool",
    "create_task_activity_tool",
    "get_town_by_cp_tool",
    "consultar_catastro_tool",
})

# Context vars — set by the orchestrator before invoking the agent chain
_wa_id: contextvars.ContextVar[str] = contextvars.ContextVar("_wa_id", default="")
_phone_number_id: contextvars.ContextVar[str] = contextvars.ContextVar("_phone_number_id", default="")
_wa_channel: contextvars.ContextVar[str] = contextvars.ContextVar("_wa_channel", default="")
_wait_msg_sent: contextvars.ContextVar[bool] = contextvars.ContextVar("_wait_msg_sent", default=False)
_client_name: contextvars.ContextVar[str] = contextvars.ContextVar("_client_name", default="")


def set_wa_context(wa_id: str, phone_number_id: str, channel: str, client_name: str = "") -> None:
    """Set WhatsApp context for the current request (called by orchestrator)."""
    _wa_id.set(wa_id or "")
    _phone_number_id.set(phone_number_id or "")
    _wa_channel.set(channel or "")
    _wait_msg_sent.set(False)
    _client_name.set(client_name or "")


def get_client_name() -> str:
    """Return the OCR-extracted client name for the current request."""
    return _client_name.get()


def get_wa_id() -> str:
    """Return the current WhatsApp ID (phone number) for the request."""
    return _wa_id.get()


def get_wa_channel() -> str:
    """Return the current channel (whatsapp, aichat, etc.)."""
    return _wa_channel.get()


class WaitMessageCallback(BaseCallbackHandler):
    """Sends a 'please wait' WhatsApp message on the first qualifying tool call."""

    def on_tool_start(self, serialized: Dict[str, Any], input_str: str, **kwargs) -> None:
        tool_name = serialized.get("name", "")
        if tool_name in _EXCLUDED_TOOLS:
            return
        if _wait_msg_sent.get(False):
            return

        wa_id = _wa_id.get("")
        phone_id = _phone_number_id.get("")
        channel = _wa_channel.get("")

        if not wa_id or not phone_id or channel != "whatsapp":
            return

        _wait_msg_sent.set(True)
        try:
            from services.zoa_client import send_whatsapp_response_sync
            send_whatsapp_response_sync(text=_WAIT_MESSAGE, company_id=phone_id, wa_id=wa_id)
            logger.info(f"[REQUEST_CONTEXT] Wait message sent to {wa_id}")
        except Exception:
            logger.exception("[REQUEST_CONTEXT] Failed to send wait message")
