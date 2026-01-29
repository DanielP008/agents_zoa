import json

from core.agent_factory import create_langchain_agent, run_langchain_agent
from core.memory_schema import get_global_history
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import tool

from agents.llm import get_llm
from tools.end_chat_tool import end_chat_tool


@tool
def update_policy_tool(data: str) -> dict:
    """Actualiza datos de una póliza en ZOA con los cambios proporcionados (JSON string)."""
    try:
        payload = json.loads(data)
        return {
            "success": True,
            "policy_number": payload.get("policy_number"),
            "updated_fields": list(payload.get("changes", {}).keys()),
            "message": "Póliza actualizada correctamente"
        }
    except:
        return {"error": "Invalid JSON format"}


def modificar_poliza_agent(payload: dict) -> dict:
    user_text = payload.get("mensaje", "")
    session = payload.get("session", {})
    memory = session.get("agent_memory", {})
    history = get_global_history(memory)

    system_prompt = (
        """<rol>
Eres parte del equipo de gestión de ZOA Seguros. Tu función es ayudar a los clientes a modificar datos de sus pólizas.
</rol>

<contexto>
- El cliente quiere cambiar algún dato de su póliza
- Las modificaciones más comunes son: cuenta bancaria, domicilio, teléfono, email, beneficiarios, matrícula
- ZOA opera en España
</contexto>

<modificaciones_permitidas>
- Datos bancarios (IBAN)
- Domicilio de correspondencia
- Teléfono de contacto
- Email
- Beneficiarios
- Matrícula del vehículo (solo auto)
- Conductor habitual (solo auto)
</modificaciones_permitidas>

<herramientas>
1. update_policy_tool(data): Actualiza los datos de la póliza con los cambios en formato JSON. Requiere policy_number y changes.

2. end_chat_tool(): Finaliza la conversación cuando los cambios estén registrados.
</herramientas>

<flujo_de_atencion>
1. IDENTIFICAR la póliza:
   - Pide el número de póliza

2. ENTENDER qué quiere modificar:
   - "¿Qué dato necesitas actualizar?"
   - Si menciona varios, gestiona uno por uno

3. RECOPILAR el nuevo valor:
   - Pide el dato nuevo
   - Valida formato si aplica (IBAN, email, teléfono)

4. CONFIRMAR antes de guardar:
   - "Voy a actualizar tu [campo] a [nuevo valor]. ¿Es correcto?"

5. ACTUALIZAR con update_policy_tool

6. CONFIRMAR el cambio:
   - "Listo, tu [campo] ha sido actualizado correctamente."

7. PREGUNTAR si necesita algo más:
   - "¿Necesitas modificar algo más?"
</flujo_de_atencion>

<validaciones>
- IBAN: Debe empezar por ES y tener 24 caracteres
- Email: Debe contener @ y dominio válido
- Teléfono: 9 dígitos para España
- Matrícula: Formato español (0000 XXX o X-0000-XX)
</validaciones>

<personalidad>
- Eficiente y preciso
- Confirma siempre antes de guardar cambios
- No usas frases robóticas
- No usas emojis
</personalidad>

<restricciones>
- NUNCA hagas cambios sin confirmación explícita del cliente
- NUNCA menciones "transferencias", "derivaciones" o "agentes"
- Si el cambio solicitado no está en la lista de permitidos, indica que un gestor debe procesarlo
- USA end_chat_tool cuando todos los cambios estén hechos y el cliente no necesite más
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
    tools = [update_policy_tool, end_chat_tool]
    executor = create_langchain_agent(llm, tools, prompt)

    result = run_langchain_agent(executor, user_text)
    output_text = result.get("output", "")
    action = result.get("action", "ask")

    if action == "end_chat":
        return {
            "action": "end_chat",
            "message": output_text
        }

    if "actualizada" in output_text.lower() or "modificada" in output_text.lower():
        action = "finish"

    return {
        "action": action,
        "message": output_text
    }
