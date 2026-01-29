"""Herramienta para finalizar conversaciones."""
from langchain_core.tools import tool


@tool
def end_chat_tool() -> dict:
    """Finaliza la conversación y limpia la sesión."""
    return {
        "action": "end_chat",
        "message": "¡Perfecto! Fue un placer ayudarte. Si necesitas algo más en el futuro, aquí estaré. ¡Que tengas un excelente día! 😊",
        "cleanup_session": True
    }