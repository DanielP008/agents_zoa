import json
from langchain_core.tools import tool
from services.zoa_client import create_task_activity

@tool
def create_refund_request_tool(data: str) -> dict:
    """Registra una solicitud de devolución creando una tarea para el gestor (JSON string).
    Campos esperados: company_id, nif, policy_number, reason, amount, iban, phone (opcional)."""
    try:
        payload = json.loads(data)
        
        # Extraer campos
        company_id = payload.get("company_id")
        nif = payload.get("nif")
        policy_number = payload.get("policy_number", "No especificada")
        reason = payload.get("reason", "No especificado")
        amount = payload.get("amount", "No especificado")
        iban = payload.get("iban", "No especificado")
        phone = payload.get("phone")
        wa_id = payload.get("wa_id")
        
        if not company_id:
            return {"error": "company_id is required"}
        
        # Construir descripción para el gestor
        description = f"""Solicitud de devolución:
- Póliza: {policy_number}
- Motivo: {reason}
- Importe: {amount}
- IBAN destino: {iban}
- NIF: {nif or 'No proporcionado'}

El cliente solicita devolución. Verificar datos y procesar."""
        
        # Crear tarea + actividad
        task_data = {
            "company_id": company_id,
            "title": f"Devolución - Póliza {policy_number}",
            "description": description,
            "card_type": "task",
            "type_of_activity": "call",
            "activity_title": "Gestionar devolución",
            "activity_description": f"Contactar al cliente para gestionar devolución de {amount}",
        }
        
        if nif:
            task_data["nif"] = nif
        if phone:
            task_data["phone"] = phone
        if wa_id:
            task_data["mobile"] = wa_id
        
        result = create_task_activity(**task_data)
        
        # Si fue exitoso, devolver mensaje amigable
        if result.get("success") or result.get("status") == "success":
            return {
                "success": True,
                "message": "Solicitud de devolución registrada. Un gestor se pondrá en contacto contigo para tramitarla."
            }
        else:
            return result
            
    except json.JSONDecodeError:
        return {"error": "Invalid JSON format"}
    except Exception as e:
        return {"error": str(e)}
