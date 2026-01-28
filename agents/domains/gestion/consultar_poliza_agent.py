import json
from typing import Any, Dict, Optional

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import tool

from agents.llm import get_llm
from core.agent_factory import create_langchain_agent, run_langchain_agent
from core.memory_schema import get_global_history
from tools.ERP_client import get_client_policys, get_policy_document_from_erp
from tools.ocr_client import extract_text


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
    company_id = payload.get("phone_number_id") or session.get("company_id", "")

    if not nif:
        return {
            "action": "ask",
            "message": "Para consultar tu póliza necesito tu NIF/DNI/NIE. ¿Me lo indicás?",
        }

    state = _get_state(memory)
    ramo = state.get("ramo")
    ocr_text = state.get("ocr_text")
    policy_id = state.get("policy_id")
    policies = state.get("policies")

    @tool
    def get_client_policys_tool(nif: str, ramo: str) -> dict:
        """Devuelve las pólizas del cliente para un ramo."""
        return get_client_policys(nif, ramo, company_id=company_id)

    @tool
    def get_policy_document_tool(nif: str, policy_id: str) -> dict:
        """Devuelve el PDF de póliza para un ID."""
        return get_policy_document_from_erp(nif, policy_id, company_id=company_id)

    @tool
    def ocr_policy_document_tool(mime_type: str, data: str) -> dict:
        """Convierte un PDF base64 en texto OCR."""
        return extract_text({"mime_type": mime_type, "data": data})

    system_prompt = (
        "Eres el agente de Consulta de Póliza.\n"
        "Paso 1: Pide el ramo (hogar, auto, pyme/comercio, responsabilidad civil, comunidades vecinos).\n"
        "Si el usuario escribe con errores o sinónimos, infiere el ramo correcto.\n"
        "Paso 2: Con NIF y ramo, usa get_client_policys_tool(nif, ramo).\n"
        "Paso 3: Identifica la póliza correcta por el ID que mencione el cliente.\n"
        "Paso 4: Usa get_policy_document_tool(nif, policy_id) para obtener el PDF.\n"
        "Paso 5: Si el usuario pregunta sobre la póliza, usa ocr_policy_document_tool.\n"
        "Si falta el identificador de póliza, pedilo.\n"
        f"Ramo_actual: {ramo or ''}"
    )
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", "{system_prompt}"),
            *get_global_history(memory),
            ("human", "{user_text}"),
        ]
    )

    llm = get_llm()
    tools = [get_client_policys_tool, get_policy_document_tool, ocr_policy_document_tool]
    executor = create_langchain_agent(llm, tools, prompt)

    result = run_langchain_agent(
        executor,
        user_text,
        system_prompt=system_prompt,
        nif=nif,
        ocr_text=ocr_text or "",
        policy_id=policy_id or "",
        policies=policies or [],
    )
    output_text = result.get("output", "")

    memory_patch = _state_patch(
        memory,
        {
            "ramo": ramo or state.get("ramo"),
            "policies": policies,
            "policy_id": policy_id,
            "ocr_text": ocr_text,
        },
    )
    for step in result.get("intermediate_steps", []):
        if not isinstance(step, tuple) or len(step) < 2:
            continue
        agent_action = step[0]
        tool_result = step[1]
        tool_name = getattr(agent_action, "tool", None)
        tool_input = getattr(agent_action, "tool_input", None)

        if tool_name == "get_client_policys_tool" and tool_input:
            ramo_value = None
            if isinstance(tool_input, dict):
                ramo_value = tool_input.get("ramo")
            elif isinstance(tool_input, str):
                try:
                    parsed = json.loads(tool_input)
                    if isinstance(parsed, dict):
                        ramo_value = parsed.get("ramo")
                except json.JSONDecodeError:
                    pass
            if isinstance(ramo_value, str):
                memory_patch = _state_patch(memory, {"ramo": ramo_value})
            if isinstance(tool_result, dict):
                policies = tool_result.get("policies")
                if isinstance(policies, list):
                    memory_patch = _state_patch(
                        memory,
                        {"ramo": ramo_value or ramo, "policies": policies},
                    )

        if tool_name == "get_policy_document_tool" and tool_input:
            policy_id = None
            if isinstance(tool_input, dict):
                policy_id = tool_input.get("policy_id")
            elif isinstance(tool_input, str):
                try:
                    parsed = json.loads(tool_input)
                    if isinstance(parsed, dict):
                        policy_id = parsed.get("policy_id")
                except json.JSONDecodeError:
                    pass
            if policy_id:
                memory_patch = _state_patch(
                    memory,
                    {"ramo": ramo or "", "policy_id": policy_id},
                )

        if isinstance(tool_result, dict) and tool_result.get("status") == "success":
            if tool_result.get("text"):
                current_ramo = (
                    ramo
                    or memory.get("domains", {})
                    .get("gestion", {})
                    .get("consultar_poliza", {})
                    .get("ramo")
                )
                memory_patch = _state_patch(
                    memory,
                    {"ramo": current_ramo, "ocr_text": tool_result["text"]},
                )

    return {
        "action": "ask",
        "message": output_text,
        "memory": memory_patch,
    }
