"""Tool to send a WhatsApp message to the current client."""
import logging
from langchain.tools import tool
from services.zoa_client import send_whatsapp_response

logger = logging.getLogger(__name__)


@tool
def send_whatsapp_tool(text: str, company_id: str, wa_id: str) -> str:
    """
    Envía un mensaje de WhatsApp al cliente.

    Usa esta herramienta cuando necesites enviar información escrita al cliente
    durante una llamada telefónica (por ejemplo, números de teléfono de asistencia).

    Args:
        text: El texto del mensaje a enviar por WhatsApp.
        company_id: El ID de la empresa (company_id).
        wa_id: El número de teléfono del cliente (wa_id).

    Returns:
        Confirmación del envío o mensaje de error.
    """
    try:
        result = send_whatsapp_response(text=text, company_id=company_id, wa_id=wa_id)
        logger.info(f"[SEND_WHATSAPP_TOOL] Message sent to {wa_id}: {text[:80]}...")
        return "Mensaje de WhatsApp enviado correctamente al cliente."
    except Exception as e:
        logger.error(f"[SEND_WHATSAPP_TOOL] Error sending WhatsApp: {e}", exc_info=True)
        return f"Error al enviar WhatsApp: {str(e)}"
