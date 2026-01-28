import json

from core.agent_factory import create_langchain_agent, run_langchain_agent
from core.memory_schema import get_global_history
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import tool

from agents.llm import get_llm
from tools.zoa_client import create_claim as zoa_create_claim, create_task_with_activity
from tools.end_chat_tool import end_chat_tool


def apertura_siniestro_agent(payload: dict) -> dict:
    user_text = payload.get("mensaje", "")
    session = payload.get("session", {})
    memory = session.get("agent_memory", {})
    history = get_global_history(memory)
    
    company_id = payload.get("phone_number_id") or session.get("company_id", "")
    wa_id = payload.get("wa_id")
    global_mem = memory.get("global", {})
    nif_value = global_mem.get("nif")

    @tool
    def create_claim_tool(data: str) -> dict:
        """Registra un siniestro en ZOA (JSON string)."""
        try:
            payload_data = json.loads(data)
            claim_result = zoa_create_claim(payload_data)
            
            if claim_result.get("success") or claim_result.get("status") == "success":
                claim_id = claim_result.get("claim_id", "unknown")
                case_type = payload_data.get("case_type", "siniestro")
                attachments = global_mem.get("attachments", [])
                
                task_result = create_task_with_activity(
                    task_description=f"Seguimiento de siniestro {case_type} - ID: {claim_id}",
                    client_nif=nif_value or "00000000T",
                    company_id=company_id,
                    wa_id=wa_id,
                    priority="high",
                    activity_type="call",
                    attachments=attachments,
                    context=payload_data,
                )
                
                claim_result["task_created"] = task_result.get("success", False)
                if task_result.get("task_id"):
                    claim_result["task_id"] = task_result["task_id"]
            
            return claim_result
        except Exception as e:
            return {"error": f"Invalid JSON format or processing error: {str(e)}"}

    system_prompt = (
        "Eres el agente de Apertura de Siniestros de ZOA. "
        "Primero identifica el tipo de siniestro: Auto, Hogar, Comunidades de vecinos, PYME/Comercio, Responsabilidad Civil. "
        "Si no está claro, pregunta con esas opciones. "
        "Luego pide la información en el orden exacto correspondiente al tipo, "
        "una pregunta por vez y sin saltarte pasos. "
        "Cuando tengas todo, usa la tool 'create_claim_tool' con un JSON string "
        "que incluya case_type y answers con los campos recopilados. "
        "Responde siempre en español y confirma la acción al usuario. "
        "\n\nOrden exacto por tipo:"
        "\nAuto:"
        "\n1) ¿Ha sido el culpable?"
        "\n2) Fecha, hora y lugar del siniestro"
        "\n3) ¿Tiene el parte amistoso?"
        "\n4) ¿A qué taller quiere llevarlo?"
        "\n5) ¿Qué día le viene bien llevarlo al taller?"
        "\n6) Fotos de los daños y del parte amistoso (solicítalas)"
        "\nHogar:"
        "\n1) Fecha, hora y lugar del siniestro"
        "\n2) ¿Cuáles fueron los daños?"
        "\n3) Fotos de los daños (solicítalas)"
        "\nComunidades de vecinos:"
        "\n1) ¿El daño se ha originado en una zona común (bajantes, fachada, tejado) o en una vivienda privada?"
        "\n2) ¿Hay vecinos particulares afectados?"
        "\n3) Fecha, hora y lugar del siniestro"
        "\n4) ¿Cuáles fueron los daños?"
        "\n5) Fotos de los daños (solicítalas)"
        "\nPYME/Comercio:"
        "\n1) Fecha, hora y lugar del siniestro"
        "\n2) ¿Cuáles fueron los daños?"
        "\n3) ¿El siniestro impide abrir el negocio?"
        "\n4) ¿Se ha dañado stock comercial o maquinaria?"
        "\n5) ¿El local ha quedado desprotegido?"
        "\n6) ¿Ha causado daños a bienes de clientes?"
        "\n7) Fotos de los daños (solicítalas)"
        "\nResponsabilidad Civil:"
        "\n1) Nombre completo, teléfono y correo electrónico de la persona que reclama"
        "\n2) ¿Qué daño ha causado a un tercero?"
        "\n3) ¿Daño material, lesiones personales, o perjuicio económico?"
        "\n4) ¿Hay denuncias?"
        "\n5) ¿Hay testigos?"
        "\n\nFormato esperado para la tool:"
        '\n{"case_type":"auto|hogar|comunidades_vecinos|pyme_comercio|responsabilidad_civil",'
        '"answers":{...}}'
        "\n\nIMPORTANTE: "
        "- Usa 'end_chat_tool' cuando el siniestro esté completamente registrado y el usuario no necesite nada más. "
        "- NO uses 'end_chat_tool' si el usuario hace preguntas adicionales o necesita otro tipo de ayuda. "
        "- Sé inteligente: analiza si la conversación ha terminado realmente o si el usuario podría necesitar más asistencia."
    )

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", "{system_prompt}"),
            *history,
            ("human", "{user_text}"),
        ]
    )

    llm = get_llm()
    tools = [create_claim_tool, end_chat_tool]
    executor = create_langchain_agent(llm, tools, prompt)

    result = run_langchain_agent(executor, user_text, system_prompt=system_prompt)
    output_text = result.get("output", "")
    action = result.get("action", "ask")

    if action == "end_chat":
        return {
            "action": "end_chat",
            "message": output_text
        }

    return {
        "action": action,
        "message": output_text
    }
