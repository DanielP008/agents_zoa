"""
Simulate the wildix card agent flow by sending requests directly to zoa_agents.
Bypasses zoa_buffer entirely — tests only the agent + card creation path.

Usage:
    python test_card_flow.py [--url URL]

Default URL: https://zoa-agents-673887944015.europe-southwest1.run.app
"""

import json
import time
import urllib.request
import urllib.error
import sys

BASE_URL = "https://zoa-agents-673887944015.europe-southwest1.run.app"

if "--url" in sys.argv:
    idx = sys.argv.index("--url")
    BASE_URL = sys.argv[idx + 1]

COMPANY_ID = "521783407682043"
USER_ID = "cdc8b949-0e6f-4c7e-805c-b1fff53a2f58"
CALL_ID = f"test_card_{int(time.time())}"

def send_insurance_agent(message: str):
    payload = {
        "action": "insurance_agent",
        "option": "process",
        "company_id": COMPANY_ID,
        "user_id": USER_ID,
        "call_id": CALL_ID,
        "message": message,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        BASE_URL,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    print(f"\n{'='*60}")
    print(f">>> Sending: {message!r}")
    print(f"    call_id: {CALL_ID}")
    print(f"    url: {BASE_URL}")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8")
            result = json.loads(body)
            print(f"<<< Response ({resp.getcode()}): {json.dumps(result, indent=2, ensure_ascii=False)}")
            return result
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        print(f"<<< ERROR ({e.code}): {body}")
        return None
    except Exception as e:
        print(f"<<< ERROR: {e}")
        return None


print(f"Test Card Flow — call_id: {CALL_ID}")
print(f"Target: {BASE_URL}")
print()

# Step 1: Send a message that should CREATE a card
print("STEP 1: Create card (mention insurance + auto)")
r1 = send_insurance_agent(
    "Hola buenas tardes, quiero tarificar un seguro de auto, "
    "me llamo Daniel Pulgar Soriano"
)

if r1 and r1.get("estado") == "creado":
    print("\n>>> Card CREATED successfully!")
elif r1:
    print(f"\n>>> Card NOT created. estado={r1.get('estado')}")
    print("    This might be because the prompt update hasn't been deployed yet.")

time.sleep(2)

# Step 2: Send a message that should UPDATE the card
print("\n\nSTEP 2: Update card (add DNI + birthdate)")
r2 = send_insurance_agent(
    "Mi DNI es 23940602V, naci el 31 de diciembre del 2000, soy hombre y soltero"
)

if r2 and r2.get("estado") == "actualizado":
    print("\n>>> Card UPDATED successfully!")
elif r2:
    print(f"\n>>> Card NOT updated. estado={r2.get('estado')}")

time.sleep(2)

# Step 3: Send another update with more data
print("\n\nSTEP 3: Update card (add postal code + license date)")
r3 = send_insurance_agent(
    "Mi codigo postal es el 46025 y saque el carnet el 15 de junio de 2019"
)

if r3 and r3.get("estado") == "actualizado":
    print("\n>>> Card UPDATED successfully!")
elif r3:
    print(f"\n>>> Card NOT updated. estado={r3.get('estado')}")

print(f"\n{'='*60}")
print("Test complete. Check zoa_agents logs for details.")
print(f"Search for call_id: {CALL_ID}")
