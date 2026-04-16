# Diagrama de Secuencia: Llamada Wildix → Teléfonos de Asistencia

## Flujo completo (caso éxito: teléfonos encontrados)

```mermaid
sequenceDiagram
    participant U as Usuario (Voz)
    participant W as Wildix Voice Bot
    participant H as handler.py<br>(handle_request)
    participant WH as wildix_handler.py<br>(handle_wildix)
    participant DB as PostgreSQL<br>(SessionManager)
    participant O as orchestrator.py<br>(process_message)
    participant R as receptionist_agent
    participant CS as classifier_siniestros
    participant TA as telefonos_asistencia_agent
    participant LLM as Gemini (LLM)
    participant ERP as ERP Client<br>(get_assistance_phones)

    Note over U,W: === TURNO 1: Primera interacción ===
    U->>W: [Habla] "Hola, necesito ayuda"
    W->>H: POST webhook {sessionId, event: {type: "reply", text: "Hola..."}}
    H->>H: Detecta sessionId+botId+event → Wildix
    H-->>H: print [WILDIX_FINAL_MESSAGE]
    H->>WH: handle_wildix(request)
    WH->>DB: try_lock_session(session_id, bot_id)
    DB-->>WH: true (lock adquirido)
    WH->>O: process_message(payload)
    
    O->>DB: get_session(session_id, bot_id)
    DB-->>O: {target_agent: "receptionist_agent", memory: {}}
    
    Note over O: _handle_nif_and_welcome()
    O->>O: NIF no encontrado en mensaje
    O->>O: Buscar NIF en CRM por teléfono
    O-->>O: NIF encontrado (ej: 23940602V)
    O->>DB: update_agent_memory (guardar NIF)
    
    Note over O: Primera interacción → Welcome message
    O-->>WH: {message: "¡Hola! Soy Sofía...¿En qué puedo ayudarte?"}
    WH->>W: POST /sessions/{id}/say "¡Hola! Soy Sofía..."
    W-->>U: [TTS] "¡Hola! Soy Sofía..."
    WH->>DB: unlock_session(session_id, bot_id)

    Note over U,W: === TURNO 2: Usuario pide asistencia ===
    U->>W: [Habla] "Necesito teléfonos de asistencia"
    W->>H: POST webhook {event: {type: "reply", text: "Necesito teléfonos..."}}
    H->>WH: handle_wildix(request)
    WH->>DB: try_lock_session(session_id, bot_id)
    DB-->>WH: true
    WH->>O: process_message(payload)
    
    O->>DB: get_session()
    DB-->>O: {target_agent: "receptionist_agent", nif: "23940602V"}
    O->>O: NIF existe, welcomed=true → continuar

    Note over O: Routing chain (silent, sin mensaje)
    rect rgb(240, 240, 255)
        O->>R: route_request("receptionist_agent", payload)
        R->>LLM: Clasificar: "Necesito teléfonos de asistencia"
        LLM-->>R: {domain: "siniestros", confidence: 0.95}
        R-->>O: {action: "route", next_agent: "classifier_siniestros_agent", message: null}
        
        Note over O: action=route, message=null → silent route (continue loop)
        O->>DB: set_target_agent → classifier_siniestros_agent
        
        O->>CS: route_request("classifier_siniestros_agent", payload)
        CS->>LLM: Clasificar dentro de siniestros
        LLM-->>CS: {route: "telefonos_asistencia_agent", confidence: 0.9}
        CS-->>O: {action: "route", next_agent: "telefonos_asistencia_agent", message: null}
        
        Note over O: action=route, message=null → silent route (continue loop)
        O->>DB: set_target_agent → telefonos_asistencia_agent
        
        O->>TA: route_request("telefonos_asistencia_agent", payload)
        TA->>LLM: "Necesito teléfonos..." + system prompt
        LLM-->>TA: "¿De qué tipo de seguro? (Auto, Hogar...)"
        TA-->>O: {action: "ask", message: "¿De qué tipo de seguro...?"}
    end
    
    Note over O: action=ask → break loop, guardar memoria
    O->>DB: update_agent_memory (historial + tool_calls)
    O-->>WH: {message: "¿De qué tipo de seguro...?", agent: "telefonos_asistencia_agent"}
    WH->>W: POST /sessions/{id}/say "¿De qué tipo de seguro...?"
    W-->>U: [TTS] "¿De qué tipo de seguro...?"
    WH->>DB: unlock_session(session_id, bot_id)

    Note over U,W: === TURNO 3: Usuario indica ramo ===
    U->>W: [Habla] "De auto"
    W->>H: POST webhook {event: {type: "reply", text: "De auto"}}
    H->>WH: handle_wildix(request)
    WH->>DB: try_lock_session → true
    WH->>O: process_message(payload)
    
    O->>DB: get_session()
    DB-->>O: {target_agent: "telefonos_asistencia_agent"}
    
    Note over O: target_agent ya es telefonos → directo (sin routing chain)
    O->>TA: route_request("telefonos_asistencia_agent", payload)
    
    rect rgb(230, 255, 230)
        TA->>LLM: "De auto" + historial
        LLM->>ERP: get_assistance_phones(nif="23940602V", ramo="AUTO", company_id="xxx")
        ERP-->>LLM: {phones: ["900 123 456", "900 789 012"]}
        LLM-->>TA: "Tus teléfonos de asistencia son: 900 123 456..."
        Note over TA: + pregunta "¿Necesitas ayuda con algo más?"
    end
    
    TA-->>O: {action: "ask", message: "Tus teléfonos son... ¿Necesitas algo más?"}
    O->>DB: update_agent_memory
    O-->>WH: {message: "Tus teléfonos son... ¿Necesitas algo más?"}
    WH->>W: POST /sessions/{id}/say
    W-->>U: [TTS] "Tus teléfonos son... ¿Necesitas algo más?"
    WH->>DB: unlock_session

    Note over U,W: === TURNO 4A: Usuario dice NO → end_chat + hangup ===
    U->>W: [Habla] "No, gracias"
    W->>H: POST webhook
    H->>WH: handle_wildix(request)
    WH->>DB: try_lock_session → true
    WH->>O: process_message(payload)
    O->>TA: route_request("telefonos_asistencia_agent")
    
    rect rgb(255, 230, 230)
        TA->>LLM: "No, gracias"
        LLM-->>TA: end_chat_tool() activado
        TA-->>O: {action: "end_chat", message: "¡Un placer! Que tengas buen día."}
    end
    
    O->>DB: delete_session(session_id)
    O-->>WH: {status: "completed", session_deleted: true, message: "¡Un placer!..."}
    WH->>W: POST /sessions/{id}/say "¡Un placer!..."
    WH->>W: POST /sessions/{id}/hangup
    W-->>U: [TTS] "¡Un placer!..." → cuelga
    WH->>DB: unlock_session
```

## Flujo alternativo 4B: Usuario quiere seguir → redirect

```mermaid
sequenceDiagram
    participant U as Usuario (Voz)
    participant W as Wildix
    participant WH as wildix_handler
    participant O as orchestrator
    participant TA as telefonos_asistencia
    participant R as receptionist_agent
    participant LLM as Gemini

    Note over U,W: Después de recibir teléfonos + "¿Necesitas algo más?"
    U->>W: [Habla] "Sí, quiero consultar una póliza"
    W->>WH: POST webhook
    WH->>O: process_message(payload)
    O->>TA: route_request("telefonos_asistencia_agent")
    
    rect rgb(255, 255, 220)
        TA->>LLM: "Sí, quiero consultar una póliza"
        LLM-->>TA: redirect_to_receptionist_tool() activado
        Note over TA: output = "__REDIRECT_TO_RECEPTIONIST__"
        TA-->>O: {action: "route", next_agent: "receptionist_agent", message: ""}
    end
    
    Note over O: Silent route → receptionist reclasifica
    O->>R: route_request("receptionist_agent", payload)
    R->>LLM: Clasificar "quiero consultar una póliza"
    LLM-->>R: {domain: "gestion"}
    R-->>O: {action: "route", next_agent: "classifier_gestion_agent"}
    Note over O: Continúa routing chain hacia gestión...
```

## Protección contra mensajes concurrentes (session lock)

```mermaid
sequenceDiagram
    participant U as Usuario
    participant W as Wildix
    participant WH as wildix_handler
    participant DB as PostgreSQL

    U->>W: [Habla] "Necesito ayuda con mi seguro"
    W->>WH: POST webhook (final event #1)
    WH->>DB: try_lock_session → true ✅
    Note over WH: Procesando agentes... (3-5 seg)
    
    U->>W: [Murmura algo bajo]
    W->>WH: POST webhook (final event #2)
    WH->>DB: try_lock_session → false ❌
    WH-->>W: {status: "ignored", reason: "session_busy"}
    Note over WH: print "[WILDIX] Session X busy, ignoring: '...'"
    
    Note over WH: ...agentes terminan
    WH->>W: POST /say (respuesta del event #1)
    WH->>DB: unlock_session ✅
```
