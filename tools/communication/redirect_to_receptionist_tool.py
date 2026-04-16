"""Tool to redirect user back to receptionist for other inquiries."""
from langchain.tools import tool

@tool(return_direct=True)
def redirect_to_receptionist_tool() -> str:
    """
    Redirige al usuario a la recepcionista para continuar con otra consulta.
    
    Usar cuando:
    - El usuario indica que quiere hacer otra consulta diferente
    - El usuario dice "sí, necesito algo más" o similar
    - El usuario menciona un tema diferente al actual (ej: estaba en siniestros pero pregunta por una póliza nueva)
    
    NO usar cuando:
    - El usuario dice que no necesita nada más (usar end_chat_tool)
    - El usuario se despide
    """
    return "__REDIRECT_TO_RECEPTIONIST__"
