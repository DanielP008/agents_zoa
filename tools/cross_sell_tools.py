import json
from langchain_core.tools import tool

@tool
def get_customer_policies_tool(customer_id: str) -> dict:
    """Obtiene las pólizas actuales de un cliente para identificar oportunidades de venta cruzada."""
    try:
        return {
            "success": True,
            "policies": [
                {
                    "policy_number": "POL-11111",
                    "type": "Auto",
                    "coverage": "Terceros Completo",
                    "vehicle": "Ford Focus 2020"
                }
            ],
            "recommendations": [
                "Upgrade a Todo Riesgo",
                "Agregar cobertura de granizo",
                "Seguro de hogar"
            ]
        }
    except Exception as e:
        return {"error": str(e)}

@tool
def create_cross_sell_offer_tool(data: str) -> dict:
    """Registra una oferta de venta cruzada en ZOA (JSON string)."""
    try:
        payload = json.loads(data)
        return {
            "success": True,
            "offer_id": "OFF-54321",
            "product": payload.get("product"),
            "discount": "15%",
            "message": "Oferta registrada. Te contactará un asesor en las próximas 24hs."
        }
    except:
        return {"error": "Invalid JSON format"}
