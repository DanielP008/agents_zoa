import json
from langchain.tools import tool
from services.zoa_client import create_task_activity

@tool
def update_policy_tool(data: str) -> dict:
    """Actualiza datos de una póliza creando una tarea para el gestor (JSON string).
    Campos esperados: company_id, nif, policy_number, changes (dict), phone (opcional)."""
    try:
        payload = json.loads(data)
        
        # Extraer campos
        company_id = payload.get("company_id")
        nif = payload.get("nif")
        policy_number = payload.get("policy_number", "No especificada")
        changes = payload.get("changes", {})
        phone = payload.get("phone")
        wa_id = payload.get("wa_id")
        
        if not company_id:
            return {"error": "company_id is required"}
        if not changes:
            return {"error": "changes is required"}
        
        # Construir descripción de cambios
        changes_str = "\n".join([f"- {key}: {value}" for key, value in changes.items()])
        
        description = f"""Solicitud de modificación de póliza:
- Póliza: {policy_number}
- NIF: {nif or 'No proporcionado'}

Cambios solicitados:
{changes_str}

El cliente solicita estos cambios. Verificar datos y actualizar póliza."""
        
        # Crear tarea + actividad
        task_data = {
            "company_id": company_id,
            "title": f"Modificar Póliza {policy_number}",
            "description": description,
            "card_type": "task",
            "type_of_activity": "call",
            "activity_title": "Gestionar modificación",
            "activity_description": f"Contactar al cliente para confirmar y aplicar cambios en póliza {policy_number}",
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
                "policy_number": policy_number,
                "updated_fields": list(changes.keys()),
                "message": "Solicitud de modificación registrada. Un gestor verificará los cambios y te confirmará."
            }
        else:
            return result
            
    except json.JSONDecodeError:
        return {"error": "Invalid JSON format"}
    except Exception as e:
        return {"error": str(e)}
