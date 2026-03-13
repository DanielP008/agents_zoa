"""Tools for creating and updating insurance tarification cards via ZOA AI Chat.

Used by the wildix_card_agent to manage auto_sheet and home_sheet cards
during phone call transcription processing.
"""

import json
import logging
from langchain.tools import tool
from services.zoa_client import create_aichat_card, update_aichat_card

logger = logging.getLogger(__name__)

_card_state: dict = {"ramo_activo": None, "card_created": False, "card_data": {}}
_call_context: dict = {"company_id": "", "user_id": "", "call_id": ""}


def set_call_context(company_id: str, user_id: str, call_id: str):
    """Set the call context used by create/update tools. Called by the agent before invocation."""
    _call_context["company_id"] = company_id
    _call_context["user_id"] = user_id
    _call_context["call_id"] = call_id


def get_card_state() -> dict:
    """Return current card state set by the last tool invocation."""
    return dict(_card_state)


def reset_card_state():
    _card_state["ramo_activo"] = None
    _card_state["card_created"] = False
    _card_state["card_data"] = {}


def create_card_tool(
    body_type: str,
    company_id: str = None,
    user_id: str = None,
    call_id: str = None,
    data: dict = None,
    complete: bool = False
) -> dict:
    """
    Crea una nueva tarjeta de tarificación (auto o hogar) en ZOA.
    
    Can be called directly (Python args) or via LangChain tool (JSON string).
    """
    # Handle direct Python call (e.g. from handler)
    if isinstance(body_type, str) and not body_type.startswith("{"):
        payload = {
            "body_type": body_type,
            "data": data or {},
            "complete": complete
        }
        # Use provided context or fallback to global context
        ctx_company = company_id or _call_context["company_id"]
        ctx_user = user_id or _call_context["user_id"]
        ctx_call = call_id or _call_context["call_id"]
        
    else:
        # Handle LangChain tool call (JSON string in first arg)
        try:
            payload = json.loads(body_type)
        except json.JSONDecodeError as e:
            return {"error": f"JSON inválido: {e}"}
        
        ctx_company = _call_context["company_id"]
        ctx_user = _call_context["user_id"]
        ctx_call = _call_context["call_id"]

    final_body_type = payload.get("body_type")
    if final_body_type not in ("auto_sheet", "home_sheet"):
        return {"error": "body_type debe ser 'auto_sheet' o 'home_sheet'"}

    card_data = payload.get("data", {})
    is_complete = payload.get("complete", False)

    result = create_aichat_card(
        company_id=ctx_company,
        user_id=ctx_user,
        call_id=ctx_call,
        body_type=final_body_type,
        data=card_data,
        complete=bool(is_complete),
    )

    if "error" not in result:
        ramo = "AUTO" if final_body_type == "auto_sheet" else "HOGAR"
        _card_state["ramo_activo"] = ramo
        _card_state["card_created"] = True
        _card_state["card_data"] = card_data
        logger.info(f"[CARD_TOOLS] Card created: ramo={ramo}")

    return result


@tool
def create_card_tool_wrapper(data: str) -> dict:
    """
    Crea una nueva tarjeta de tarificación (auto o hogar) en ZOA.

    SOLO usar si NO existe una tarjeta creada previamente (card_created=false en el estado).
    Se puede llamar UNA SOLA VEZ por sesión.

    Input: JSON string con:
    - body_type: "auto_sheet" o "home_sheet"
    - complete: boolean (false por defecto)
    - data: objeto con los datos extraídos (vehiculo, tomador, vivienda, poliza_actual)

    Ejemplo AUTO:
    {"body_type": "auto_sheet", "complete": false, "data": {"vehiculo": {"matricula": "1234ABC"}, "tomador": {"nombre": "Juan", "dni": "12345678A"}, "poliza_actual": {}}}

    Ejemplo HOGAR:
    {"body_type": "home_sheet", "complete": false, "data": {"tomador": {"nombre": "Ana"}, "vivienda": {"nombre_via": "Gran Via", "tipo_vivienda": "PISO_EN_ALTO"}, "poliza_actual": {}}}
    """
    return create_card_tool(data)


@tool
def update_card_tool(data: str) -> dict:
    """
    Actualiza una tarjeta de tarificación existente en ZOA.

    SOLO usar si ya existe una tarjeta creada (card_created=true en el estado).
    Envía SIEMPRE el objeto consolidado completo (datos anteriores + nuevos).

    Input: JSON string con:
    - body_type: "auto_sheet" o "home_sheet"
    - complete: boolean (false por defecto, true si TODOS los campos obligatorios están rellenos)
    - data: objeto consolidado completo (memoria + datos nuevos)

    Los campos sin dato van como cadena vacía "".
    """
    try:
        payload = json.loads(data)
    except json.JSONDecodeError as e:
        return {"error": f"JSON inválido: {e}"}

    body_type = payload.get("body_type")
    if body_type not in ("auto_sheet", "home_sheet"):
        return {"error": "body_type debe ser 'auto_sheet' o 'home_sheet'"}

    card_data = payload.get("data", {})
    complete = payload.get("complete", False)

    result = update_aichat_card(
        company_id=_call_context["company_id"],
        user_id=_call_context["user_id"],
        call_id=_call_context["call_id"],
        body_type=body_type,
        data=card_data,
        complete=bool(complete),
    )

    if "error" not in result:
        _card_state["card_data"] = card_data
        logger.info(f"[CARD_TOOLS] Card updated: ramo={_card_state.get('ramo_activo')}")

    return result


def update_card_tool_direct(
    body_type: str,
    data: dict = None,
    complete: bool = False,
) -> dict:
    """
    Direct Python call to update a tarification card (no JSON parsing needed).
    Used by the optimized wildix_card_agent to avoid LangChain tool overhead.
    """
    if body_type not in ("auto_sheet", "home_sheet"):
        return {"error": "body_type debe ser 'auto_sheet' o 'home_sheet'"}

    card_data = data or {}

    result = update_aichat_card(
        company_id=_call_context["company_id"],
        user_id=_call_context["user_id"],
        call_id=_call_context["call_id"],
        body_type=body_type,
        data=card_data,
        complete=bool(complete),
    )

    if "error" not in result:
        _card_state["card_data"] = card_data
        logger.info(f"[CARD_TOOLS] Card updated (direct): ramo={_card_state.get('ramo_activo')}")

    return result