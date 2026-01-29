import json

from core.agent_factory import create_langchain_agent, run_langchain_agent
from core.memory_schema import get_global_history
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import tool

from agents.llm import get_llm
from tools.end_chat_tool import end_chat_tool


@tool
def get_policy_info_tool(policy_number: str) -> dict:
    """Obtiene información de una póliza desde ZOA dado su número."""
    try:
        # TODO: Implement actual ZOA API call to get policy info
        return {
            "success": True,
            "policy_number": policy_number,
            "holder": "Juan Pérez",
            "coverage": "Todo Riesgo",
            "vehicle": "Ford Focus 2020",
            "expiration": "2026-12-31",
            "premium": "$15,000/mes"
        }
    except Exception as e:
        return {"error": str(e)}


def consultar_poliza_agent(payload: dict) -> dict:
    user_text = payload.get("mensaje", "")
    session = payload.get("session", {})
    memory = session.get("agent_memory", {})
    history = get_global_history(memory)

    system_prompt = (
        """<rol>
Eres parte del equipo de gestión de ZOA Seguros. Tu función es ayudar a los clientes a consultar información de sus pólizas.
</rol>

<contexto>
- El cliente quiere saber información sobre su póliza (coberturas, vencimientos, datos, etc.)
- Puedes consultar la información en el sistema
- ZOA opera en España con pólizas de Auto, Hogar, PYME/Comercio, RC y Comunidades
</contexto>

<herramientas>
1. get_policy_info_tool(policy_number): Obtiene toda la información de una póliza por su número.

2. end_chat_tool(): Finaliza la conversación cuando el cliente tenga la información que necesitaba.
</herramientas>

<flujo_de_atencion>
1. IDENTIFICAR la póliza:
   - Pide el número de póliza
   - Si no lo tiene, pregunta por matrícula (auto), dirección (hogar) o nombre de empresa (comercio)

2. CONSULTAR con get_policy_info_tool

3. PRESENTAR la información:
   - Si pregunta algo específico, responde solo eso
   - Si pregunta "todo sobre mi póliza", presenta de forma organizada:
     * Tipo de seguro y cobertura
     * Bien asegurado (vehículo, dirección, etc.)
     * Fecha de vencimiento
     * Prima (coste)
     * Forma de pago

4. PREGUNTAS FRECUENTES:
   - "¿Estoy cubierto si...?" → Consulta las coberturas y responde según lo que incluya
   - "¿Cuándo vence?" → Fecha exacta de vencimiento
   - "¿Cuánto pago?" → Prima y periodicidad
   - "¿Qué cubre mi seguro?" → Lista de coberturas principales
</flujo_de_atencion>

<personalidad>
- Informativo y claro
- Paciente para explicar términos de seguros si el cliente no los entiende
- No usas frases robóticas
- No usas emojis
</personalidad>

<restricciones>
- NUNCA inventes coberturas o datos que no estén en el sistema
- NUNCA menciones "transferencias", "derivaciones" o "agentes"
- Si el cliente pregunta por algo que no está en la información disponible, indica que un gestor puede ampliar la información
- USA end_chat_tool cuando el cliente tenga toda la información y confirme que no necesita más
</restricciones>"""
    )

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system_prompt),
            *history,
            ("human", "{user_text}"),
        ]
    )

    llm = get_llm()
    tools = [get_policy_info_tool, end_chat_tool]
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
