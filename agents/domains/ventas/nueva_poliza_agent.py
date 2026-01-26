import json

from core.agent_factory import create_langchain_agent, run_langchain_agent
from core.memory_schema import get_global_history
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import tool

from agents.llm import get_llm


@tool
def create_quote_tool(data: str) -> dict:
    """Genera una cotización de seguro en ZOA con los datos proporcionados (JSON string)."""
    try:
        payload = json.loads(data)
        # TODO: Implement actual ZOA API call for quotes
        return {
            "success": True,
            "quote_id": "COT-12345",
            "premium": "$12,500/mes",
            "coverage": payload.get("coverage_type", "Terceros Completo"),
            "message": "Cotización generada exitosamente"
        }
    except:
        return {"error": "Invalid JSON format"}


@tool
def create_new_policy_tool(data: str) -> dict:
    """Crea una nueva póliza en ZOA con los datos proporcionados (JSON string)."""
    try:
        payload = json.loads(data)
        # TODO: Implement actual ZOA API call to create policy
        return {
            "success": True,
            "policy_number": "POL-98765",
            "message": "Póliza creada exitosamente. Te enviaremos los detalles por email."
        }
    except:
        return {"error": "Invalid JSON format"}


def nueva_poliza_agent(payload: dict) -> dict:
    user_text = payload.get("mensaje", "")
    session = payload.get("session", {})
    memory = session.get("agent_memory", {})
    history = get_global_history(memory)

    system_prompt = (
        "Eres el agente de Nuevas Pólizas de ZOA. "
        "Tu objetivo es ayudar al cliente a cotizar y contratar una nueva póliza de seguro automotor. "
        "Proceso: "
        "1. Primero genera una cotización (necesitas: tipo de vehículo, modelo, año, uso, zona). "
        "2. Presenta las opciones disponibles (Terceros, Terceros Completo, Todo Riesgo). "
        "3. Si el cliente acepta, procede con la contratación (necesitas: datos personales, DNI, datos del vehículo, forma de pago). "
        "Pregunta de manera conversacional y amable. "
        "Usa 'create_quote_tool' para cotizar y 'create_new_policy_tool' para contratar. "
        "Responde siempre en español, sé profesional y orientado a ventas pero sin presionar."
    )

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system_prompt),
            *history,
            ("human", "{user_text}"),
        ]
    )

    llm = get_llm()
    tools = [create_quote_tool, create_new_policy_tool]
    executor = create_langchain_agent(llm, tools, prompt)

    result = run_langchain_agent(executor, user_text)
    output_text = result.get("output", "")

    # Check if we are done (policy created?)
    action = "ask"
    if "pol-" in output_text.lower() or "póliza creada" in output_text.lower():
        action = "finish"

    return {
        "action": action,
        "message": output_text
    }
