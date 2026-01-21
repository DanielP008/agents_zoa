import requests
import json
import uuid
import sys

def main():
    print("=== ZOA Agents Local CLI ===")
    print("Asegúrate de que el contenedor Docker esté corriendo (docker compose up)")
    print("Endpoint: http://localhost:8080")
    print("Escribe 'quit' o 'exit' para salir.\n")

    # Configuration
    url = "http://localhost:8080"
    user_id = "local_tester_001"
    company_id = "company_123" # Default from simulation script
    conversation_id = str(uuid.uuid4())

    print(f"Session ID: {conversation_id}")
    print(f"User ID: {user_id}\n")

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
            "from": user_id,
            "text": user_input,
            "company_id": company_id,
            "conversation_id": conversation_id
        }

        try:
            response = requests.post(url, json=payload)
            response.raise_for_status()
            
            data = response.json()
            # The handler returns {"status": "ok", "response": ...}
            # The orchestrator response structure depends on implementation, 
            # usually it has 'message' or similar.
            
            agent_response = data.get("response", {})
            
            # Handle different response types if necessary
            if isinstance(agent_response, dict):
                message = agent_response.get("message", str(agent_response))
            else:
                message = str(agent_response)

            print(f"Agente: {message}\n")

        except requests.exceptions.ConnectionError:
            print(f"Error: No se pudo conectar a {url}. ¿Está corriendo el contenedor Docker?\n")
        except Exception as e:
            print(f"Error: {e}\n")

if __name__ == "__main__":
    main()
