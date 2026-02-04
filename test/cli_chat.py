import requests
import json
import uuid
import sys

def main():
    print("=== ZOA Agents Local CLI ===")
    print("Asegúrate de que el contenedor Docker esté corriendo (docker compose up)")
    print("Endpoint: http://localhost:8080")
    print("Escribe 'quit' o 'exit' para salir.\n")

    url = "http://localhost:8080"
    user_id = "+34777666999"
    company_id = "606338959237848"      # ZOA => 521783407682043        ERP -> 606338959237848
    user_name = "Juan Pérez"
    #user_nif = "27464443M"              # ZOA => 23940602V              ERP => 27464443M
    conversation_id = f"{company_id}_{user_id}"

    print(f"Session ID: {conversation_id}")
    print(f"User ID (wa_id): {user_id}")

    while True:
        try:
            user_input = input("Tú: ").strip()
        except EOFError:
            break

        if user_input.lower() in ['quit', 'exit']:
            print("Bye!")
            break

        if not user_input:
            continue

        payload = {
            "wa_id": user_id,
            "mensaje": user_input,
            "phone_number_id": company_id,
            "name": user_name,
        }

        try:
            response = requests.post(url, json=payload)
            response.raise_for_status()
            
            data = response.json()
            agent_response = data.get("response", {})
            
            if isinstance(agent_response, dict):
                agent = agent_response.get("agent")
                status = agent_response.get("status")
                session_deleted = agent_response.get("session_deleted", False)
                next_agent = agent_response.get("next_agent")
                response_type = agent_response.get("type", "unknown")
                
                if agent:
                    print(f"AGENTE ACTUAL: {agent}")
                elif next_agent:
                    print(f"AGENTE ACTUAL: {next_agent} (transición)")
                else:
                    print(f"AGENTE ACTUAL: unknown (tipo: {response_type})")
                
                message = agent_response.get("message", str(agent_response))
                
                # Check if conversation ended
                if status == "completed":
                    print(f"Agente: {message}")
                    print("\n" + "="*50)
                    print("🔒 CONVERSACIÓN FINALIZADA")
                    if session_deleted:
                        print("✓ Sesión eliminada de PostgreSQL")
                    else:
                        print("⚠️ Sesión NO fue eliminada")
                    print("="*50 + "\n")
                    print("La conversación ha terminado. Saliendo...")
                    break
            else:
                print(f"AGENTE ACTUAL: unknown")
                message = str(agent_response)

            print(f"Agente: {message}\n")

        except requests.exceptions.ConnectionError:
            print(f"Error: No se pudo conectar a {url}. ¿Está corriendo el contenedor Docker?\n")
        except Exception as e:
            print(f"Error: {e}\n")

if __name__ == "__main__":
    main()
