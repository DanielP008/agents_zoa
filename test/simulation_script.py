import os
import sys
import json
from unittest.mock import patch

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Set env var to use Mock DB
os.environ["USE_CLOUD_SQL"] = "false"
os.environ["ZOA_ENDPOINT_URL"] = "http://mock-endpoint" # Dummy URL to avoid error in client import/usage if verified

from core.orchestrator import process_message
from core.tracing import setup_tracing

# Initialize tracing
setup_tracing()


# Mock the ZOA client tool to avoid network calls
@patch("core.orchestrator.send_whatsapp_response")
def run_simulation(mock_send):
    print("=== STARTING CONVERSATION SIMULATION ===\n")

    # Define the conversation flow
    # Scenario: User wants to report a car accident
    conversation_flow = [
        "Hola, necesito ayuda",
        "Quiero denunciar un choque",
        "Fue en la calle Corrientes 1234",
        "Si, tengo los datos del tercero",
        "Gracias"
    ]

    # Context
    user_id = "5491112345678"
    company_id = "company_123"
    
    # Mock return for send_whatsapp_response so code doesn't break if it expects something
    mock_send.return_value = {"status": "success", "mocked": True}

    for i, user_text in enumerate(conversation_flow):
        print(f"--- Step {i+1} ---")
        print(f"User ({user_id}): {user_text}")

        # Payload structure expected by handler/orchestrator
        payload = {
            "from": user_id,
            "text": user_text,
            "company_id": company_id,
            "conversation_id": "conv_abc123"
        }

        # Process
        result = process_message(payload)
        
        # Display Agent Response
        print(f"Agent Action: {result.get('type')}")
        print(f"Agent Message: {result.get('message')}")
        
        # Check if external tool was called (the whatsapp message)
        if mock_send.called:
            # Get the args of the last call
            args, kwargs = mock_send.call_args
            # mock_send is called as: send_whatsapp_response(text=..., company_id=..., ...)
            sent_text = kwargs.get('text')
            print(f"[ZOA API Call] Sending Message: {sent_text}")
            mock_send.reset_mock()
        
        print("\n")

if __name__ == "__main__":
    run_simulation()
