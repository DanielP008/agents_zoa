"""Tool to transfer a Wildix call to a PBX extension."""
from langchain.tools import tool


@tool(return_direct=True)
def transfer_call_tool(extension: str) -> str:
    """
    Transfiere la llamada del cliente a una extensión interna de la centralita.

    Usar cuando:
    - El cliente está en horario de oficina y necesita hablar con un departamento concreto.
    - Ya se ha identificado a qué departamento corresponde la consulta del cliente.

    Args:
        extension: Número de extensión al que transferir (ej: "201", "202").
    """
    return f"__TRANSFER_CALL__:{extension}"
