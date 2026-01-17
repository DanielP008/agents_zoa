import os
import requests

# Default to a mock URL if not set
ZOA_MCP_URL = os.environ.get("ZOA_MCP_URL", "http://mock-mcp:8080")


def _call_zoa_mcp(tool_name: str, args: dict) -> dict:
    """Helper to call the external ZOA MCP Cloud Function."""
    # If in dev/mock mode, return fake data directly to avoid network errors
    if ZOA_MCP_URL == "http://mock-mcp:8080":
        return _mock_response(tool_name, args)

    try:
        resp = requests.post(
            ZOA_MCP_URL,
            json={"tool": tool_name, "args": args},
            timeout=10,
            headers={"Content-Type": "application/json"},
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return {"error": f"Failed to call ZOA MCP: {str(e)}"}


def _mock_response(tool_name: str, args: dict) -> dict:
    """Fallback mock data for local dev without a real MCP URL."""
    if tool_name == "create_claim":
        return {
            "status": "created",
            "claim_id": "ZOA-MOCK-999",
            "payload": args,
        }
    if tool_name == "fetch_policy":
        pol = args.get("policy_number", "UNKNOWN")
        return {
            "policy_number": pol,
            "holder": "Cliente Mock",
            "status": "active",
            "coverage": "Full Mock Coverage",
        }
    return {"error": "Unknown mock tool"}


def create_claim(payload: dict) -> dict:
    """Registra un siniestro via MCP."""
    return _call_zoa_mcp("create_claim", payload)


def fetch_policy(policy_number: str) -> dict:
    """Obtiene datos de poliza via MCP."""
    return _call_zoa_mcp("fetch_policy", {"policy_number": policy_number})
