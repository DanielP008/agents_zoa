# ZOA Agents

Sistema de agentes de IA para automatización de atención al cliente en brokers de seguros.  
Recibe mensajes de WhatsApp y los procesa mediante una jerarquía de agentes especializados.

---

## Arquitectura

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              MENSAJE ENTRANTE                               │
│                         (WhatsApp via Buffer System)                        │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              app/handler.py                                 │
│                           (Cloud Function Entry)                            │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           core/orchestrator.py                              │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │  1. Cargar sesión (PostgreSQL)                                         │ │
│  │  2. Preparar memoria (ensure_memory_shape)                             │ │
│  │  3. Llamar al agente actual (target_agent)                             │ │
│  │  4. Si passthrough → llamar siguiente agente en el mismo turno         │ │
│  │  5. Persistir cambios en DB                                            │ │
│  │  6. Enviar respuesta a WhatsApp                                        │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          routers/main_router.py                             │
│                      (Dispatch determinístico a agentes)                    │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
              ┌───────────────────────┼───────────────────────┐
              ▼                       ▼                       ▼
┌─────────────────────┐   ┌─────────────────────┐   ┌─────────────────────┐
│   RECEPTIONIST      │   │  DOMAIN CLASSIFIER  │   │  SPECIALIST AGENT   │
│  (receptionist_     │   │  (classifier_       │   │  (apertura_,        │
│   agent.py)         │   │   siniestros_agent) │   │   consulta_, etc)   │
└─────────────────────┘   └─────────────────────┘   └─────────────────────┘
```

---

## Flujo de Mensaje

```
Usuario: "Tuve un choque"

1. Handler recibe mensaje
2. Orchestrator carga sesión (target_agent = receptionist_agent)
3. Receptionist clasifica → domain = "siniestros"
4. Receptionist devuelve: { action: "route", next_agent: "classifier_siniestros_agent", message: null }
5. Orchestrator detecta passthrough (message = null) → llama inmediatamente al classifier
6. Classifier responde: "¿Querés denunciar un siniestro nuevo o consultar uno existente?"
7. Orchestrator persiste target_agent = classifier_siniestros_agent en DB
8. Usuario recibe respuesta del classifier (sin mensaje intermedio del receptionist)
```

---

## Jerarquía de Agentes

```
receptionist_agent
    │
    ├── classifier_siniestros_agent
    │       ├── apertura_siniestro_agent
    │       ├── consulta_estado_agent
    │       └── telefonos_asistencia_agent
    │
    ├── classifier_gestion_agent (pendiente)
    │       └── ...
    │
    └── classifier_ventas_agent (pendiente)
            └── ...
```

Configuración en `contracts/routes.json`:

```json
{
  "default": "receptionist_agent",
  "domains": {
    "siniestros": {
      "receptionist_label": "siniestros",
      "classifier": "classifier_siniestros_agent",
      "specialists": [
        "telefonos_asistencia_agent",
        "apertura_siniestro_agent",
        "consulta_estado_agent"
      ]
    }
  }
}
```

---

## Acciones de Agentes

| Action   | Descripción                                      | message     | Comportamiento                              |
|----------|--------------------------------------------------|-------------|---------------------------------------------|
| `ask`    | Preguntar al usuario, quedarse en el mismo agente | requerido   | Envía mensaje, espera respuesta             |
| `route`  | Derivar a otro agente                            | opcional    | Si null → passthrough (responde el siguiente) |
| `finish` | Terminar flujo, volver al receptionist           | requerido   | Envía mensaje, resetea sesión               |

### Passthrough Routing

Cuando un agente devuelve `route` con `message: null`, el orchestrator **no envía mensaje** y llama inmediatamente al siguiente agente en el mismo turno.

```python
# Passthrough (el classifier responde en el mismo turno)
return {
    "action": "route",
    "next_agent": "classifier_siniestros_agent",
    "domain": "siniestros",
    "message": None
}

# Route tradicional (se envía mensaje, siguiente turno habla el nuevo agente)
return {
    "action": "route",
    "next_agent": "apertura_siniestro_agent",
    "domain": "siniestros",
    "message": "Te derivo con el agente de apertura."
}
```

---

## Schema de Memoria (`agent_memory`)

La memoria se persiste en `sessions.agent_memory` (PostgreSQL) y sigue esta estructura:

```json
{
  "global": {
    "language": "es",
    "summary": "Resumen de la conversación",
    "last_agent": "classifier_siniestros_agent",
    "last_action": "ask",
    "last_domain": "siniestros",
    "preferences": {}
  },
  "conversation_history": [
    {
      "role": "user",
      "text": "Tuve un choque",
      "timestamp": "2026-01-23T12:45:00Z",
      "agent": "receptionist_agent",
      "domain": null,
      "action": "input"
    }
  ],
  "domains": {
    "siniestros": {
      "state": "collecting_data",
      "fields": {}
    }
  },
  "agents": {
    "classifier_siniestros_agent": {
      "history": [],
      "data": {
        "last_route": "apertura_siniestro_agent",
        "confidence": 0.82
      }
    }
  },
  "metadata": {
    "version": 1,
    "updated_at": "2026-01-23T12:45:00Z"
  }
}
```

### Reglas de Escritura

| Componente    | Escribe en                          | Responsable   |
|---------------|-------------------------------------|---------------|
| `global`      | `global.*`                          | Orchestrator  |
| `conversation_history` | `conversation_history[]`   | Orchestrator  |
| `domains`     | `domains.<domain>.*`                | Agentes       |
| `agents`      | `agents.<agent_name>.*`             | Agentes       |
| `metadata`    | `metadata.*`                        | Orchestrator  |

---

## Estructura del Proyecto

```
zoa_agents/
├── agents/
│   ├── domains/
│   │   └── siniestros/
│   │       ├── classifier_agent.py      # Clasifica intención dentro del dominio
│   │       ├── apertura_siniestro_agent.py
│   │       ├── consulta_estado_agent.py
│   │       └── telefonos_asistencia_agent.py
│   ├── llm.py                           # Configuración de LLM (Gemini)
│   └── receptionist_agent.py            # Clasificador de dominio inicial
├── app/
│   └── handler.py                       # Entrypoint Cloud Function
├── contracts/
│   ├── agent_contracts.md               # Documentación de contratos
│   ├── routes.json                      # Configuración de routing
│   └── message_schema.json              # Schema de mensajes
├── core/
│   ├── agent_allowlist.py               # Validación de rutas permitidas
│   ├── db.py                            # PostgreSQL session manager
│   ├── memory_schema.py                 # Helpers para agent_memory
│   └── orchestrator.py                  # Orquestación del flujo
├── routers/
│   └── main_router.py                   # Dispatch a agentes
├── tools/
│   ├── ocr_client.py                    # Cliente OCR
│   └── zoa_client.py                    # Cliente ERP ZOA
├── test/
│   ├── cli_chat.py                      # CLI para testing local
│   └── simulation_script.py
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

---

## Tech Stack

| Componente       | Tecnología                    |
|------------------|-------------------------------|
| LLM              | Google Gemini (Flash/Pro)     |
| Framework        | LangChain                     |
| Hosting          | Google Cloud Run / Functions  |
| Base de Datos    | PostgreSQL (Cloud SQL)        |
| Runtime          | Python 3.11                   |
| Contenedor       | Docker                        |

---

## Setup

### Variables de Entorno

Copiar `.env.example` a `.env`:

```bash
cp .env.example .env
```

Variables requeridas:
- `GEMINI_API_KEY` - API key de Google AI
- `GEMINI_MODEL` - Modelo a usar (ej: `gemini-1.5-flash`)
- Credenciales de DB (hardcodeadas en `core/db.py` por ahora)

### Ejecución Local (Docker)

```bash
docker compose up --build
```

El servicio estará en `http://localhost:8080`

### Ejecución Local (venv)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

## Testing

### CLI Chat

```bash
python3 test/cli_chat.py
```

### cURL

```bash
curl -X POST http://localhost:8080 \
  -H "Content-Type: application/json" \
  -d '{
    "wa_id": "5491155551234",
    "mensaje": "Hola, tuve un choque",
    "phone_number_id": "company_123"
  }'
```

### Reset de Sesión

```bash
curl -X POST http://localhost:8080 \
  -H "Content-Type: application/json" \
  -d '{
    "wa_id": "5491155551234",
    "mensaje": "BORRAR_POSTGRESS_INFO",
    "phone_number_id": "company_123"
  }'
```

---

## Contratos

Ver documentación completa en [`contracts/agent_contracts.md`](contracts/agent_contracts.md)

---

## Roadmap

- [ ] Implementar `classifier_gestion_agent`
- [ ] Implementar `classifier_ventas_agent`
- [ ] Agregar summary automático de conversación
- [ ] Migrar credenciales DB a variables de entorno
- [ ] Agregar tests unitarios
