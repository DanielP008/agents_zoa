import json
from typing import Any, Dict

from langchain.tools import tool

from core.llm import get_llm
from agents.domains.common.generic_knowledge_agent import generic_knowledge_agent
from core.agent_factory import create_langchain_agent, run_langchain_agent
from core.memory_schema import get_global_history
from tools.zoa.tasks import create_task_activity_tool
from tools.communication.end_chat_tool import end_chat_tool
from tools.erp.erp_tools import (
    get_client_policys_tool,
    get_policy_document_tool,
    ocr_policy_document_tool
)


RAMO_OPTIONS = [
    "hogar",
    "auto",
    "pyme/comercio",
    "responsabilidad civil",
    "comunidades vecinos",
]


def _get_state(memory: Dict[str, Any]) -> Dict[str, Any]:
    return (
        memory.get("domains", {})
        .get("gestion", {})
        .get("consultar_poliza", {})
        or {}
    )


def _state_patch(memory: Dict[str, Any], updates: Dict[str, Any]) -> Dict[str, Any]:
    domain_data = memory.get("domains", {}).get("gestion", {}) or {}
    current = domain_data.get("consultar_poliza", {}) or {}
    new_state = {**current, **updates}
    return {"domains": {"gestion": {**domain_data, "consultar_poliza": new_state}}}


def consultar_poliza_agent(payload: dict) -> dict:
    user_text = (payload.get("mensaje") or "").strip()
    session = payload.get("session", {})
    memory = session.get("agent_memory", {})
    global_mem = memory.get("global", {})
    nif = global_mem.get("nif")
    company_id = payload.get("erp_company_id") or payload.get("phone_number_id", "")
    wa_id = payload.get("wa_id")
    history = get_global_history(memory)

    state = _get_state(memory)
    ramo = state.get("ramo")
    ocr_text = state.get("ocr_text")
    policy_id = state.get("policy_id")
    policies = state.get("policies")

    @tool
    def ask_expert_knowledge(query: str) -> str:
        """Consulta al agente experto en seguros para responder dudas GENÉRICAS.
        Usar cuando la pregunta es sobre conceptos, coberturas generales o dudas que no requieren datos del cliente."""
        sub_payload = {
            "mensaje": query,
            "session": session
        }
        result = generic_knowledge_agent(sub_payload)
        return result.get("message", "No pude obtener respuesta del experto.")

    system_prompt = f"""<rol>
Eres parte del equipo de gestión de ZOA Seguros. Tu función es ayudar a los clientes a consultar información de sus pólizas.
</rol>

<contexto>
- El cliente quiere saber información sobre su póliza (coberturas, vencimientos, datos, etc.)
- Puedes consultar la información en el sistema si tienes el NIF del cliente.
- Si la pregunta es GENÉRICA (teoría de seguros, coberturas generales), consulta al experto.
- ZOA opera en España con pólizas de Auto, Hogar, PYME/Comercio, RC y Comunidades.
</contexto>

<variables_actuales>
NIF_actual: {nif or 'NO_IDENTIFICADO'}
Ramo_actual: {ramo or 'No especificado'}
Company_ID: {company_id}
</variables_actuales>

<herramientas>
1. get_client_policys_tool(nif, ramo, company_id): Obtiene las pólizas de un ramo específico.
   - IMPORTANTE: Siempre usa company_id="{company_id}"
2. get_policy_document_tool(nif, policy_id, company_id): Descarga el documento de la póliza.
   - IMPORTANTE: Siempre usa company_id="{company_id}"
3. ocr_policy_document_tool(mime_type, data): Lee documentos enviados por el usuario.
4. ask_expert_knowledge(query): Responde dudas genéricas sin datos de cliente.
5. create_task_activity_tool(json_string): Crea tarea manual cuando NO tenemos NIF.
   - USAR SI NIF_actual es "NO_IDENTIFICADO".
   - JSON debe incluir:
     - company_id: "{company_id}"
     - title: "Consulta Póliza - Usuario No Identificado"
     - description: "Usuario sin NIF intenta consultar póliza. Mensaje: [mensaje del usuario]"
     - card_type: "opportunity"
     - pipeline_name: "Revisiones"
     - stage_name: "Nuevo"
     - type_of_activity: "whatsapp"
     - activity_title: "Identificar usuario"
     - wa_id: "{wa_id or ''}"
6. end_chat_tool(): Finaliza la conversación.
</herramientas>

<flujo_de_atencion>
1. ANALIZA LA CONSULTA:
   - ¿Es GENÉRICA? -> Usa ask_expert_knowledge inmediatamente.
   - ¿Es ESPECÍFICA (quiere ver SU póliza)? -> Sigue al paso 2.

2. VERIFICA IDENTIDAD (NIF):
   - Si NIF_actual es vacío o "NO_IDENTIFICADO":
     - NO pidas el NIF (debería venir identificado).
     - Usa create_task_activity_tool explicando la situación.
     - Dile al usuario que un gestor revisará su caso.
   - Si tienes NIF: Sigue al paso 3.

3. CONSULTAR PÓLIZA:
   - Si no tienes el ramo (Auto, Hogar...), pídelo.
   - Usa get_client_policys_tool con el NIF y el ramo.
   - Identifica la póliza correcta con el usuario.
   - Usa get_policy_document_tool si necesita el documento.

4. PRESENTAR INFORMACIÓN:
   - Responde puntualmente a lo que pregunta.
   - Si pregunta "todo", resume: Tipo, Bien asegurado, Vencimiento, Prima, Forma de pago.
</flujo_de_atencion>

<personalidad>
- Informativo y claro
- Paciente para explicar términos
- No usas frases robóticas
- No usas emojis
</personalidad>

<restricciones>
- NUNCA inventes coberturas.
- NUNCA menciones "transferencias", "derivaciones" o "agentes".
- USA end_chat_tool cuando el cliente tenga la información y confirme que no necesita más.
</restricciones>"""

    llm = get_llm()
    tools = [
        get_client_policys_tool, 
        get_policy_document_tool, 
        ocr_policy_document_tool, 
        ask_expert_knowledge, 
        create_task_activity_tool,
        end_chat_tool
    ]
    
    agent = create_langchain_agent(llm, tools, system_prompt)
    result = run_langchain_agent(agent, user_text, history)
    
    output_text = result.get("output", "")
    action = result.get("action", "ask")
    
    if action == "end_chat":
        return {
            "action": "end_chat",
            "message": output_text
        }
    
    # State update logic
    memory_patch = _state_patch(
        memory,
        {
            "ramo": ramo or state.get("ramo"),
            "policies": policies,
            "policy_id": policy_id,
            "ocr_text": ocr_text,
        },
    )

    return {
        "action": action,
        "message": output_text,
        "memory": memory_patch,
    }
