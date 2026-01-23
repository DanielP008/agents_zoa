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
    company_id = "company_123" # Simulating the phone_number_id
    conversation_id = str(uuid.uuid4())

    print(f"Session ID: {conversation_id}")
    print(f"User ID (wa_id): {user_id}\n")

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

        # Updated to match the "Source of Truth" Buffer payload
        payload = {
            "wa_id": user_id,
            "mensaje": user_input,
            "phone_number_id": company_id,
            # conversation_id is internal to ZOA, not from Buffer, but we can send it if needed.
            # However, the Buffer contract doesn't send it, so testing without it is better
            # to mimic production.
        }

        try:
            response = requests.post(url, json=payload)
            response.raise_for_status()
            
            data = response.json()
            agent_response = data.get("response", {})
            
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
