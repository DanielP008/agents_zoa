# Testing

## CLI Chat
Run an interactive conversation:
```bash
python3 test/cli_chat.py
```

## cURL Example
```bash
curl -X POST http://localhost:8080 \
  -H "Content-Type: application/json" \
  -d '{
    "wa_id": "5491155551234",
    "mensaje": "Hi, I had an accident",
    "phone_number_id": "company_123"
  }'
```
