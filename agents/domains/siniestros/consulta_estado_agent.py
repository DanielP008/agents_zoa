import json

from core.agent_factory import create_langchain_agent, run_langchain_agent
from core.memory_schema import get_global_history
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import tool

from agents.llm import get_llm
from tools.end_chat_tool import end_chat_tool
from tools.zoa_client import fetch_policy
from tools.ocr_client import extract_text


@tool
def lookup_policy(policy_number: str) -> dict:
    """Busca informacion de una poliza por su numero."""
    return fetch_policy(policy_number)

@tool
def process_document(doc_type: str) -> dict:
    """Procesa un documento (OCR) para extraer texto. Simulado."""
    # En la realidad, aqui pasariamos la URL o el binario del documento
    return extract_text({"type": doc_type})


def consulta_estado_agent(payload: dict) -> dict:
    user_text = payload.get("mensaje", "")
    session = payload.get("session", {})
    memory = session.get("agent_memory", {})
    history = get_global_history(memory)

    system_prompt = (
        """<rol>
Eres parte del equipo de siniestros de ZOA Seguros. Tu función es informar a los clientes sobre el estado de sus siniestros ya abiertos.
</rol>

<contexto>
- El cliente quiere saber cómo va un siniestro que ya tiene abierto
- Puedes consultar el estado en el sistema
- También puedes procesar documentos que el cliente envíe (fotos de póliza, DNI, etc.)
- ZOA opera en España
</contexto>

<herramientas>
1. lookup_policy(policy_number): Busca información de una póliza y sus siniestros asociados por número de póliza.

2. process_document(doc_type): Procesa un documento enviado por el cliente para extraer información (OCR).

3. end_chat_tool(): Finaliza la conversación cuando el cliente tenga la información que necesitaba.
</herramientas>

<flujo_de_atencion>
1. IDENTIFICAR el siniestro:
   - Pide el número de póliza o el número de expediente/siniestro
   - Si el cliente envía una foto de su póliza, usa process_document para extraer el número

2. CONSULTAR en el sistema:
   - Usa lookup_policy para obtener el estado

3. INFORMAR de forma clara:
   - Estado actual del siniestro
   - Última actualización
   - Próximos pasos esperados
   - Tiempo estimado si está disponible

4. PREGUNTAS ESPECÍFICAS:
   - Si el cliente pregunta algo muy específico que no tienes (detalles de peritaje, importes exactos de indemnización), indica que un gestor le contactará con esa información

5. PREGUNTAS GENERALES (FAQs):
   - ¿Cuánto tarda en resolverse? → Depende del tipo, generalmente 15-30 días para casos simples
   - ¿Cuándo me pagan? → Una vez aprobada la valoración, 5-10 días hábiles
   - ¿Puedo añadir información? → Sí, puede enviarla por este chat
</flujo_de_atencion>

<personalidad>
- Informativo y claro
- Paciente si el cliente no tiene el número a mano
- No usas frases robóticas
- No usas emojis
- Si el cliente está frustrado por la espera, muestra comprensión sin hacer promesas que no puedas cumplir
</personalidad>

<restricciones>
- NUNCA inventes estados o información que no tengas
- NUNCA menciones "transferencias", "derivaciones" o "agentes"
- Si no encuentras el siniestro, pide confirmar los datos o indica que un gestor verificará
- USA end_chat_tool cuando el cliente tenga la información y confirme que no necesita más
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
    tools = [lookup_policy, process_document, end_chat_tool]
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
