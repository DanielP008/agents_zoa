import os
import sys
import json
import logging

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.erp_client import ERPClient

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_sinco_extraction():
    # Valores de prueba basados en la solicitud del usuario
    company_id = "521783407682043" # ID visto en logs anteriores
    num_poliza = "25781" # Valor de la imagen

    print(f"--- Iniciando prueba de SINCO para póliza {num_poliza} ---")
    
    client = ERPClient(company_id)
    
    # 1. Llamada directa para ver el JSON crudo
    print(f"Consultando ERP para póliza: {num_poliza}...")
    result = client.get_policy_by_num(num_poliza)
    
    if not result.get("success"):
        print(f"❌ Error al consultar póliza: {result.get('error')}")
        return

    policy_data_list = result.get("policy", [])
    if isinstance(policy_data_list, dict):
        policy_data_list = [policy_data_list]
        
    print(f"\n✅ Se encontraron {len(policy_data_list)} pólizas coincidentes.")

    for i, policy in enumerate(policy_data_list):
        print(f"\n--- Póliza {i+1} ---")
        print(f"Número: {policy.get('number')}")
        print(f"Ramo/Producto: {policy.get('product', {}).get('description')}")
        print(f"Riesgo: {policy.get('risk')}")
        print(f"Estado: {policy.get('status', {}).get('description')}")
        
        # Intentar extraer siniestralidad
        # Copiamos la lógica de _extract_siniestralidad aquí para probar
        def _find_field(obj, candidates):
            if not isinstance(obj, dict):
                return None
            for key in candidates:
                if key in obj:
                    return obj[key]
            # No recursivo para no ensuciar, buscamos en primer nivel
            return None

        asegurado = _find_field(policy, ["anos_asegurado", "anos_asegurados", "totalAnosAsegurado", "aniosAsegurado"])
        compania = _find_field(policy, ["anos_compania", "anos_compania_anterior", "anosCompania", "aniosCompania"])
        sin_siniestros = _find_field(policy, ["anos_sin_siniestros", "anosSinSiniestros", "aniosSinSiniestros"])
        
        if asegurado or compania or sin_siniestros:
            print(f"🎉 ¡ENCONTRADOS DATOS SINIESTRALIDAD!")
            print(f"   Años Asegurado: {asegurado}")
            print(f"   Años Compañía: {compania}")
            print(f"   Años Sin Siniestros: {sin_siniestros}")
        else:
            print("   ⚠️ No se encontraron campos de siniestralidad en el nivel superior.")

    # Buscar la póliza de ciclomotor para inspección profunda
    target_policy = None
    for p in policy_data_list:
        if "3022400225781" in str(p.get("number")):
            target_policy = p
            break
            
    if target_policy:
        print("\n✅ JSON COMPLETO de la póliza de Ciclomotor (3022400225781):")
        print(json.dumps(target_policy, indent=2, ensure_ascii=False))
    else:
        print("\n⚠️ No se encontró la póliza de ciclomotor para inspección.")

if __name__ == "__main__":
    test_sinco_extraction()
