# ZOA Agents

Sistema multi-agente de IA para automatizar la atención al cliente en brokers de seguros.  
Procesa mensajes de WhatsApp mediante una jerarquía de agentes especializados con memoria persistente.

---

## Tabla de Contenidos

- [Arquitectura](#arquitectura)
- [Flujo de Mensaje](#flujo-de-mensaje)
- [Agentes](#agentes)
- [Memoria](#memoria)
- [Configuración](#configuración)
- [Ejecución](#ejecución)
- [Testing](#testing)
- [Estructura del Proyecto](#estructura-del-proyecto)

---

## Arquitectura

### Vista General

```
                                    ┌──────────────────┐
                                    │    WhatsApp      │
                                    │  (Buffer System) │
                                    └────────┬─────────┘
                                             │
                                             ▼
┌────────────────────────────────────────────────────────────────────────────────┐
│                              ZOA AGENTS SERVICE                                │
│  ┌──────────────────────────────────────────────────────────────────────────┐  │
│  │                           app/handler.py                                 │  │
│  │                        (Cloud Function Entry)                            │  │
│  └────────────────────────────────┬─────────────────────────────────────────┘  │
│                                   │                                            │
│                                   ▼                                            │
│  ┌──────────────────────────────────────────────────────────────────────────┐  │
│  │                        core/orchestrator.py                              │  │
│  │  ┌────────────────────────────────────────────────────────────────────┐  │  │
│  │  │  1. Cargar sesión desde PostgreSQL                                 │  │  │
│  │  │  2. Preparar memoria (ensure_memory_shape)                         │  │  │
│  │  │  3. Ejecutar agente actual                                         │  │  │
│  │  │  4. Manejar passthrough si message=null                            │  │  │
│  │  │  5. Persistir cambios en DB                                        │  │  │
│  │  │  6. Enviar respuesta via ZOA API                                   │  │  │
│  │  └────────────────────────────────────────────────────────────────────┘  │  │
│  └────────────────────────────────┬─────────────────────────────────────────┘  │
│                                   │                                            │
│                                   ▼                                            │
│  ┌──────────────────────────────────────────────────────────────────────────┐  │
│  │                        routers/main_router.py                            │  │
│  │                     (Dispatch determinístico)                            │  │
│  └────────────────────────────────┬─────────────────────────────────────────┘  │
│                                   │                                            │
│           ┌───────────────────────┼───────────────────────┐                    │
│           ▼                       ▼                       ▼                    │
│  ┌─────────────────┐   ┌─────────────────────┐   ┌─────────────────────┐       │
│  │  RECEPTIONIST   │   │  DOMAIN CLASSIFIER  │   │  SPECIALIST AGENT   │       │
│  │                 │   │                     │   │                     │       │
│  │ Clasifica       │   │ Clasifica intención │   │ Ejecuta tarea       │       │
│  │ dominio         │   │ dentro del dominio  │   │ específica          │       │
│  └─────────────────┘   └─────────────────────┘   └─────────────────────┘       │
│                                                                                │
└────────────────────────────────────────────────────────────────────────────────┘
                                             │
                    ┌────────────────────────┼────────────────────────┐
                    ▼                        ▼                        ▼
           ┌─────────────────┐     ┌─────────────────┐      ┌─────────────────┐
           │   PostgreSQL    │     │    ZOA API      │      │   Gemini LLM    │
           │   (Sesiones)    │     │   (WhatsApp)    │      │                 │
           └─────────────────┘     └─────────────────┘      └─────────────────┘
```

### Jerarquía de Agentes

```
receptionist_agent
│
├── classifier_siniestros_agent
│   ├── telefonos_asistencia_agent    → Números de grúa/asistencia
│   ├── apertura_siniestro_agent      → Denunciar siniestro nuevo
│   └── consulta_estado_agent         → Consultar siniestro existente
│
├── classifier_gestion_agent          → (pendiente)
│   └── ...
│
└── classifier_ventas_agent           → (pendiente)
    └── ...
```

---

## Flujo de Mensaje

### Diagrama de Secuencia

```
Usuario          Handler       Orchestrator      Router         Receptionist    Classifier
   │                │               │               │                │              │
   │  "Tuve un      │               │               │                │              │
   │   choque"      │               │               │                │              │
   │───────────────>│               │               │                │              │
   │                │  process()    │               │                │              │
   │                │──────────────>│               │                │              │
   │                │               │  get_session()│                │              │
   │                │               │◄──────────────│                │              │
   │                │               │               │                │              │
   │                │               │  route()      │                │              │
   │                │               │──────────────>│                │              │
   │                │               │               │  handle()      │              │
   │                │               │               │───────────────>│              │
   │                │               │               │                │              │
   │                │               │               │  {action:route,│              │
   │                │               │               │   message:null}│              │
   │                │               │               │<───────────────│              │
   │                │               │               │                │              │
   │                │               │  PASSTHROUGH  │                │              │
   │                │               │  (message=null)                │              │
   │                │               │──────────────>│                │              │
   │                │               │               │  handle()      │              │
   │                │               │               │──────────────────────────────>│
   │                │               │               │                │              │
   │                │               │               │  {action:ask,  │              │
   │                │               │               │   message:"¿Querés denunciar  │
   │                │               │               │   o consultar?"}              │
   │                │               │<──────────────│<──────────────────────────────│
   │                │               │               │                │              │
   │                │               │  save_session()                │              │
   │                │               │  send_whatsapp()               │              │
   │                │               │               │                │              │
   │  "¿Querés      │<──────────────│               │                │              │
   │   denunciar    │               │               │                │              │
   │   o consultar?"│               │               │                │              │
   │                │               │               │                │              │
```

### Acciones de Agentes

| Action   | message    | Comportamiento                                           |
|----------|------------|----------------------------------------------------------|
| `ask`    | requerido  | Envía mensaje, espera respuesta, permanece en el agente  |
| `route`  | `null`     | **Passthrough**: llama al siguiente agente inmediatamente|
| `route`  | string     | Envía mensaje, cambia agente para el próximo turno       |
| `finish` | requerido  | Envía mensaje, resetea sesión al receptionist            |

### Passthrough Routing

Cuando `message: null`, el orchestrator **no envía respuesta** y ejecuta el siguiente agente en el mismo turno:

```python
# Passthrough - el classifier responde inmediatamente
return {
    "action": "route",
    "next_agent": "classifier_siniestros_agent",
    "domain": "siniestros",
    "message": None
}
```

---

## Agentes

### Receptionist (`receptionist_agent.py`)

- **Función**: Clasifica el dominio del mensaje (siniestros, gestión, ventas)
- **Primera interacción**: Muestra mensaje de bienvenida si no puede clasificar
- **Interacciones posteriores**: Pide aclaración si no puede clasificar
- **Output**: Siempre `route` con passthrough o `ask` para aclarar

### Classifier Siniestros (`classifier_agent.py`)

- **Función**: Determina la intención específica dentro de siniestros
- **Opciones**: Asistencia, apertura de siniestro, consulta de estado
- **Output**: `ask` para clarificar o `route` al especialista

### Especialistas

| Agente                        | Función                                    |
|-------------------------------|--------------------------------------------|
| `telefonos_asistencia_agent`  | Provee números de grúa y asistencia        |
| `apertura_siniestro_agent`    | Recolecta datos y registra siniestro       |
| `consulta_estado_agent`       | Consulta estado de siniestros existentes   |

---

## Memoria

### Schema (`agent_memory`)

```json
{
  "global": {
    "language": "es",
    "summary": "",
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
    },
    {
      "role": "assistant",
      "text": "¿Querés denunciar o consultar?",
      "timestamp": "2026-01-23T12:45:02Z",
      "agent": "classifier_siniestros_agent",
      "domain": "siniestros",
      "action": "ask"
    }
  ],
  "domains": {},
  "agents": {
    "classifier_siniestros_agent": {
      "last_route": "apertura_siniestro_agent",
      "confidence": 0.82
    }
  },
  "metadata": {
    "version": 1,
    "updated_at": "2026-01-23T12:45:02Z"
  }
}
```

### Responsabilidades de Escritura

| Namespace              | Quién escribe   | Ejemplo                                      |
|------------------------|-----------------|----------------------------------------------|
| `global.*`             | Orchestrator    | `last_agent`, `last_action`                  |
| `conversation_history` | Orchestrator    | Cada turno user/assistant                    |
| `agents.<name>.*`      | Cada agente     | `classifier_siniestros_agent.last_route`     |
| `domains.<domain>.*`   | Agentes         | `siniestros.state`, `siniestros.fields`      |
| `metadata.*`           | Orchestrator    | `version`, `updated_at`                      |

---

## Configuración

### Variables de Entorno

Crear archivo `.env` basado en `.env.example`:

```bash
cp .env.example .env
```

**Variables requeridas:**

| Variable           | Descripción                          | Ejemplo                     |
|--------------------|--------------------------------------|-----------------------------|
| `GEMINI_API_KEY`   | API key de Google AI                 | `AIza...`                   |
| `GEMINI_MODEL`     | Modelo principal                     | `gemini-2.5-flash`          |
| `ZOA_ENDPOINT_URL` | URL del API de ZOA para WhatsApp     | `https://flow-zoa-...`      |

**Variables opcionales:**

| Variable                   | Descripción                    | Default                    |
|----------------------------|--------------------------------|----------------------------|
| `GEMINI_OCR_MODEL`         | Modelo para OCR                | `gemini-1.5-flash`         |
| `LANGSMITH_API_KEY`        | Key para tracing               | -                          |
| `LANGCHAIN_TRACING_V2`     | Activar tracing                | `false`                    |

### Base de Datos

La conexión a PostgreSQL está configurada en `core/db.py`. La tabla requerida:

```sql
CREATE TABLE sessions (
    session_id VARCHAR(255) PRIMARY KEY,
    domain VARCHAR(100),
    target_agent VARCHAR(100),
    agent_memory JSONB,
    updated_at TIMESTAMP DEFAULT NOW()
);
```

### Routing (`contracts/routes.json`)

Define la jerarquía de agentes y sus etiquetas:

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

## Ejecución

### Docker (Recomendado)

```bash
# Construir y ejecutar
docker compose up --build

# El servicio estará en http://localhost:8080
```

### Local (venv)

```bash
# Crear entorno virtual
python3 -m venv .venv
source .venv/bin/activate

# Instalar dependencias
pip install -r requirements.txt

# Ejecutar (requiere configurar DB externa)
python -m flask run --port 8080
```

---

## Testing

### CLI Chat

Herramienta interactiva para probar conversaciones:

```bash
python3 test/cli_chat.py
```

### cURL

```bash
# Mensaje normal
curl -X POST http://localhost:8080 \
  -H "Content-Type: application/json" \
  -d '{
    "wa_id": "5491155551234",
    "mensaje": "Hola, tuve un choque",
    "phone_number_id": "company_123"
  }'

# Reset de sesión
curl -X POST http://localhost:8080 \
  -H "Content-Type: application/json" \
  -d '{
    "wa_id": "5491155551234",
    "mensaje": "BORRAR_POSTGRESS_INFO",
    "phone_number_id": "company_123"
  }'
```

---

## Estructura del Proyecto

```
zoa_agents/
├── agents/
│   ├── domains/
│   │   └── siniestros/
│   │       ├── classifier_agent.py         # Clasifica intención en siniestros
│   │       ├── apertura_siniestro_agent.py # Registra siniestros nuevos
│   │       ├── consulta_estado_agent.py    # Consulta siniestros existentes
│   │       └── telefonos_asistencia_agent.py # Provee números de asistencia
│   ├── llm.py                              # Configuración de Gemini
│   └── receptionist_agent.py               # Clasifica dominio inicial
│
├── app/
│   └── handler.py                          # Entry point (Cloud Function)
│
├── contracts/
│   ├── agent_contracts.md                  # Documentación de contratos
│   ├── routes.json                         # Configuración de routing
│   └── message_schema.json                 # Schema de mensajes
│
├── core/
│   ├── agent_allowlist.py                  # Validación de rutas permitidas
│   ├── db.py                               # PostgreSQL session manager
│   ├── memory_schema.py                    # Helpers para agent_memory
│   └── orchestrator.py                     # Orquestación del flujo
│
├── routers/
│   └── main_router.py                      # Dispatch a agentes
│
├── tools/
│   ├── ocr_client.py                       # Cliente OCR
│   └── zoa_client.py                       # Cliente API ZOA (WhatsApp)
│
├── test/
│   ├── cli_chat.py                         # CLI interactivo
│   └── simulation_script.py                # Script de simulación
│
├── .env.example                            # Variables de entorno ejemplo
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

---

## Tech Stack

| Componente     | Tecnología                      |
|----------------|---------------------------------|
| LLM            | Google Gemini (Flash/Pro)       |
| Framework      | LangChain                       |
| Hosting        | Google Cloud Run                |
| Base de Datos  | PostgreSQL (Cloud SQL)          |
| Runtime        | Python 3.11                     |
| Contenedor     | Docker                          |

---

## Documentación Adicional

- [Contratos de Agentes](contracts/agent_contracts.md) - Especificación detallada de inputs/outputs
