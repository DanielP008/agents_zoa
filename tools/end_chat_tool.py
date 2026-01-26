"""
Herramienta para finalizar conversaciones de forma inteligente.
Los agentes especialistas usan esta tool cuando detectan que la consulta está resuelta.
"""
from langchain_core.tools import tool


@tool
def end_chat_tool() -> dict:
    """Finaliza la conversación cuando el usuario ya no necesita ayuda adicional.

    Usa esta herramienta cuando:
    - La consulta del usuario esté completamente resuelta
    - El usuario haya confirmado que no necesita nada más
    - La tarea solicitada se haya completado exitosamente
    - No haya más preguntas pendientes

    Esta herramienta limpiará automáticamente la sesión de la base de datos.
    """
    return {
        "action": "end_chat",
        "message": "¡Perfecto! Fue un placer ayudarte. Si necesitas algo más en el futuro, aquí estaré. ¡Que tengas un excelente día! 😊",
        "cleanup_session": True
    }