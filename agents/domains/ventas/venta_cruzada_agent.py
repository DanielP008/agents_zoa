import json

from core.agent_factory import create_langchain_agent, run_langchain_agent
from core.memory_schema import get_global_history
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import tool

from agents.llm import get_llm
from tools.end_chat_tool import end_chat_tool


@tool
def get_customer_policies_tool(customer_id: str) -> dict:
    """Obtiene las pólizas actuales de un cliente para identificar oportunidades de venta cruzada."""
    try:
        # TODO: Implement actual ZOA API call
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
        # TODO: Implement actual ZOA API call
        return {
            "success": True,
            "offer_id": "OFF-54321",
            "product": payload.get("product"),
            "discount": "15%",
            "message": "Oferta registrada. Te contactará un asesor en las próximas 24hs."
        }
    except:
        return {"error": "Invalid JSON format"}


def venta_cruzada_agent(payload: dict) -> dict:
    user_text = payload.get("mensaje", "")
    session = payload.get("session", {})
    memory = session.get("agent_memory", {})
    history = get_global_history(memory)

    system_prompt = (
        "Eres el agente de Venta Cruzada de ZOA. "
        "Tu objetivo es ofrecer productos adicionales o upgrades a clientes existentes. "
        "Proceso: "
        "1. Identifica las pólizas actuales del cliente (usa 'get_customer_policies_tool'). "
        "2. Analiza oportunidades: upgrades de cobertura, productos complementarios (hogar, vida, AP), coberturas adicionales (granizo, etc). "
        "3. Presenta las opciones de manera personalizada según lo que el cliente ya tiene. "
        "4. Si hay interés, registra la oferta con 'create_cross_sell_offer_tool'. "
        "Sé consultivo, personalizado y enfócate en el valor agregado. "
        "No seas agresivo, el cliente ya confía en ZOA. "
        "Responde siempre en español con un tono profesional y amigable. "
        "\n\nIMPORTANTE: Usa 'end_chat_tool' cuando hayas registrado una oferta de venta cruzada exitosamente y el usuario no necesite nada más. "
        "NO uses 'end_chat_tool' si el usuario solo pidió información o necesita explorar más opciones."
    )

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system_prompt),
            *history,
            ("human", "{user_text}"),
        ]
    )

    llm = get_llm()
    tools = [get_customer_policies_tool, create_cross_sell_offer_tool, end_chat_tool]
    executor = create_langchain_agent(llm, tools, prompt)

    result = run_langchain_agent(executor, user_text)
    output_text = result.get("output", "")
    action = result.get("action", "ask")

    # If end_chat_tool was used, return the special action
    if action == "end_chat":
        return {
            "action": "end_chat",
            "message": output_text
        }

    return {
        "action": action,
        "message": output_text
    }
