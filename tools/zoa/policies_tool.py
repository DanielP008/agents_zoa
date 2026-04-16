from langchain.tools import tool
from services.zoa_client import fetch_policy

@tool
def lookup_policy(policy_number: str) -> dict:
    """Busca informacion de una poliza por su numero."""
    return fetch_policy(policy_number)
