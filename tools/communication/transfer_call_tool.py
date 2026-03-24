"""Tool to transfer a Wildix call to a PBX extension."""
from langchain.tools import tool


@tool(return_direct=True)
def transfer_call_tool(extension: str) -> str:
        """
    Transfers the client's call to an internal PBX extension.
    Use when:
    - The client is within business hours and needs to talk to a specific department.
    - The department corresponding to the client's query has already been identified.
    Args:
        extension: Extension number to transfer to (e.g., "201", "202").
    """
    return f"__TRANSFER_CALL__:{extension}"
