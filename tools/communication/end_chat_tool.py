"""Herramienta para finalizar conversaciones."""
from langchain.tools import tool


@tool(return_direct=True)
def end_chat_tool() -> str:
    """
    Finaliza la conversación y limpia la sesión del usuario.
    
    Esta herramienta debe usarse cuando:
    - El usuario ha completado su consulta y está satisfecho
    - El usuario indica explícitamente que no necesita nada más
    - El usuario se despide después de recibir la información solicitada
    
    Al llamar a esta herramienta:
    - Se enviará un mensaje de despedida al usuario
    - La sesión y toda la información almacenada en PostgreSQL se eliminará automáticamente
    - El usuario deberá iniciar una nueva conversación para futuras consultas
    """
    # return_direct=True ensures the agent loop stops immediately after this tool runs.
    return "¡Perfecto! Fue un placer ayudarte. Si necesitas algo más en el futuro, aquí estaré. ¡Que tengas un excelente día!"