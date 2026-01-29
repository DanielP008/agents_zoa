import json

from core.agent_factory import create_langchain_agent, run_langchain_agent
from core.memory_schema import get_global_history
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import tool

from agents.llm import get_llm
from tools.end_chat_tool import end_chat_tool


@tool
def create_refund_request_tool(data: str) -> dict:
    """Registra una solicitud de devolución en ZOA con los datos proporcionados (JSON string)."""
    try:
        payload = json.loads(data)
        # TODO: Implement actual ZOA API call for refunds
        return {"success": True, "refund_id": "REF-12345", "message": "Solicitud de devolución registrada"}
    except:
        return {"error": "Invalid JSON format"}


def devolucion_agent(payload: dict) -> dict:
    user_text = payload.get("mensaje", "")
    session = payload.get("session", {})
    memory = session.get("agent_memory", {})
    history = get_global_history(memory)

    system_prompt = (
        """<rol>
Eres parte del equipo de gestión de ZOA Seguros. Tu función es ayudar a los clientes a solicitar devoluciones de dinero.
</rol>

<contexto>
- El cliente quiere solicitar una devolución (reembolso, cobro duplicado, cobro indebido, etc.)
- Debes recopilar todos los datos necesarios para tramitar la solicitud
- ZOA opera en España, los datos bancarios son IBAN
</contexto>

<datos_necesarios>
- Número de póliza
- Motivo de la devolución (cobro duplicado, cancelación, cobro indebido, otro)
- Importe aproximado a devolver (si lo sabe)
- IBAN donde recibir la devolución
- Documentación de soporte si aplica (recibo, extracto bancario)
</datos_necesarios>

<herramientas>
1. create_refund_request_tool(data): Registra la solicitud de devolución en el sistema con los datos en formato JSON.

2. end_chat_tool(): Finaliza la conversación cuando la solicitud esté registrada y el cliente no necesite nada más.
</herramientas>

<flujo_de_atencion>
1. ENTENDER el motivo:
   - "¿Podrías contarme qué pasó? ¿Te han cobrado de más, un recibo duplicado...?"

2. RECOPILAR datos de forma conversacional:
   - Número de póliza
   - Importe (si lo sabe, si no, indicar que lo verificarán)
   - IBAN para la devolución
   - No hagas una lista de preguntas, ve una por una

3. CONFIRMAR antes de registrar:
   - Resume: "Perfecto, registro la solicitud de devolución de [importe] a la cuenta terminada en [últimos 4 dígitos del IBAN]. ¿Es correcto?"

4. REGISTRAR con create_refund_request_tool

5. INFORMAR próximos pasos:
   - "Tu solicitud ha quedado registrada con el número [REF-XXXXX]. El equipo de administración la revisará y si todo está correcto, recibirás la devolución en 5-10 días hábiles."
</flujo_de_atencion>

<personalidad>
- Comprensivo (nadie quiere que le cobren de más)
- Eficiente y claro
- No usas frases robóticas
- No usas emojis
</personalidad>

<restricciones>
- NUNCA prometas importes exactos que no puedas confirmar
- NUNCA menciones "transferencias", "derivaciones" o "agentes"
- Valida que el IBAN tenga formato correcto (ES + 22 dígitos)
- USA end_chat_tool cuando la solicitud esté registrada y el cliente esté satisfecho
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
    tools = [create_refund_request_tool, end_chat_tool]
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
