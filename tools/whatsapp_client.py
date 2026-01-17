class WhatsAppClient:
    def __init__(self, token: str):
        self.token = token

    def send_message(self, to: str, text: str) -> bool:
        return True


def send_whatsapp_message(to: str, text: str) -> dict:
    return {
        "status": "queued",
        "to": to,
        "text": text,
    }
