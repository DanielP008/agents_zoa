TODO

-> No agrupe preguntas. Que pregunte una a una los campos necesairos.

Cuando pide parte en apertura siniestros debe pedir foto en caso de que le usuario hya dicho que lo tiene


MODIFICAR EL NIF PARA QUE SEA EN BASE A UNA FLAG DE PSOTGRESS Y QUE EL ORCHESTRATOR LO PIDA JUSTO ANTES DE EJECUTAR EL SIGUIENTE AGENTE.

Subir esto a la nube

Emepzar con el punto 1 -> Modificar llm de classifiers.

# Plan de Reducción de Latencia — ZOA Agents

## Diagnóstico basado en datos reales

Datos extraídos de `timings/request_trace.jsonl` (17 requests WhatsApp).

### Distribución promedio del tiempo por request

| Componente         | Tiempo medio | % del total |
|--------------------|-------------|-------------|
| **Agent LLM**      | ~8.6s       | ~86%        |
| **Postgres**       | ~350ms      | ~3.5%       |
| **Tool calls (ERP+ZOA)** | ~1.1s | ~11%        |
| **Overhead**       | ~300ms      | ~3%         |

### Peor caso registrado

- **Request L12**: 38.1s total, 4 agentes en cadena:
  - `receptionist_decision` → 6.3s
  - `classifier_gestion_decision` → 14.1s
  - `generic_knowledge_agent` → 10.2s
  - `consultar_poliza_agent` → 16.5s

### Observaciones clave

1. **El cuello de botella es el LLM** — representa el 86% del tiempo total.
2. **Los classifiers usan el mismo modelo que los especialistas** — todos llaman a `get_llm()` sin parámetros, que devuelve `gemini-3-flash-preview` con `temperature=0.7`.
3. **Cadenas de routing innecesarias** — `generic_knowledge_agent` aparece como paso intermedio antes del especialista real (L12, L13), sumando 10s+ sin aportar valor.
4. **Operaciones redundantes a Postgres** — `update_agent_memory` hace internamente `get_session` + `save_session` (2 queries). `set_target_agent` hace lo mismo. En el routing loop, cada iteración puede generar 4+ queries.
5. **ERP externo es lento** — `erp_get_policies` tarda entre 760ms y 6.7s.

---

## Plan de acción

### 1. Modelo ligero para classifiers

**Problema**: `receptionist_agent`, `classifier_siniestros_agent`, `classifier_gestion_agent` usan `get_llm()` que devuelve `gemini-3-flash-preview`. Estos agentes solo clasifican texto en categorías fijas con structured output — no necesitan el modelo completo.

**Archivos afectados**:
- `core/llm.py` — agregar función para modelo ligero
- `agents/receptionist_agent.py` (L114: `llm = get_llm()`)
- `agents/domains/siniestros/classifier_agent.py` (usa `get_llm()`)
- `agents/domains/gestion/classifier_agent.py` (L70: `llm = get_llm()`)

**Implementación**:
```python
# core/llm.py
def get_llm_fast(model_name: str = None):
    """LLM ligero para classifiers y decisiones de routing."""
    api_key = os.environ.get("GEMINI_API_KEY", "")
    model = model_name or os.environ.get("GEMINI_MODEL_FAST", "gemini-2.0-flash-lite")
    
    return ChatGoogleGenerativeAI(
        model=model, 
        google_api_key=api_key,
        temperature=0.2,  # Menos creatividad, más determinismo
        max_retries=2
    )
```

En cada classifier reemplazar `get_llm()` por `get_llm_fast()`.

**Impacto estimado**: Los classifiers pasarían de 3-14s a ~1-3s. En una cadena de 2 classifiers (receptionist + domain classifier), esto reduce ~10-20s.

**Riesgo**: Bajo. Los classifiers producen JSON estructurado con campos fijos (`route`, `confidence`, `needs_more_info`). Un modelo más ligero es suficiente para esta tarea.

---

### 2. Reducir round-trips a Postgres

**Problema**: En `orchestrator.py`, el routing loop ejecuta por cada iteración:
- `set_target_agent` → internamente hace `get_session` + `save_session` (L169)
- `update_agent_memory` → internamente hace `get_session` + `save_session` (L170)
- Eso son **4 queries** por cada paso de routing, cuando ya tenemos la sesión en memoria.

Además, `_handle_nif_and_welcome` llama a `update_agent_memory` (que hace get+save) incluso cuando la sesión ya está cargada en la variable local `session`.

**Archivos afectados**:
- `core/orchestrator.py` — refactorizar persistencia
- `core/db.py` — agregar método `save_session_direct` o modificar `set_target_agent`/`update_agent_memory` para aceptar sesión precargada

**Implementación**: Acumular cambios en el objeto `session` local y hacer un solo `save_session` al final de `process_message`, en vez de persistir después de cada paso intermedio.

```python
# Dentro del routing loop (orchestrator.py, ~L155-173)
# ANTES: 4 queries por iteración
session_manager.set_target_agent(wa_id, new_target, new_domain, company_id)  # get + save
session_manager.update_agent_memory(wa_id, memory, company_id)               # get + save

# DESPUÉS: 0 queries, solo actualizar en memoria
session["target_agent"] = new_target
session["domain"] = new_domain
session["agent_memory"] = memory
# El save se hace una sola vez al salir del loop
```

Agregar un `save_session` único antes de cada `return` en `process_message`.

**Impacto estimado**: En L4 (15 postgres calls, 1030ms), se reduciría a ~3-5 calls (~200-350ms). Ahorro de 600-800ms por request con cadenas de routing.

**Riesgo**: Medio-bajo. Si el proceso crashea entre pasos, se pierde el estado intermedio. Pero dado que la sesión completa se pierde de todas formas en un crash, el riesgo real es mínimo.

---

### 3. Eliminar paso intermedio por `generic_knowledge_agent`

**Problema**: En L12 y L13, `generic_knowledge_agent` se ejecuta como paso intermedio antes del especialista real, sumando 10s+ sin aportar respuesta al usuario. Este agente existe para responder preguntas genéricas de seguros, pero los classifiers lo están routeando erróneamente como paso previo.

**Archivos afectados**:
- `agents/domains/gestion/classifier_agent_prompts.py` — el prompt no lista `generic_knowledge_agent` como ruta válida, pero algo en el flujo lo invoca.
- `core/routing/routes.json` — verificar si `generic_knowledge_agent` está configurado como fallback.
- `core/routing/allowlist.py` — revisar si permite routing a `generic_knowledge_agent` desde classifiers.

**Implementación**: 
1. Auditar en qué punto del flujo se rutea a `generic_knowledge_agent` — el classifier de gestión solo devuelve `devolucion_agent`, `consultar_poliza_agent` o `modificar_poliza_agent` según su prompt, pero algo está generando el paso intermedio.
2. Si `generic_knowledge_agent` se invoca como fallback del classifier cuando `confidence` es baja, agregar una regla en el orchestrator para que baja confidence == repreguntar al usuario, no rutear a generic.
3. Restringir `generic_knowledge_agent` para que solo se active cuando se invoca explícitamente, no como paso de routing automático.

**Impacto estimado**: Elimina 10s+ de latencia en los requests donde aparece como intermediario.

**Riesgo**: Bajo. El agente genérico seguiría disponible para uso directo; solo se elimina su invocación accidental en cadenas de routing.

---

### 4. Paralelizar búsqueda NIF + Welcome

**Problema**: En `_handle_nif_and_welcome` (orchestrator.py L351-487), las operaciones se ejecutan secuencialmente:
1. `search_contact_by_phone(wa_id, company_id)` — llamada HTTP a ZOA (puede tardar 200-800ms)
2. `update_agent_memory` — 2 queries a Postgres
3. `send_whatsapp_response` — llamada HTTP a ZOA

Estos pasos son bloqueantes. La búsqueda de contacto y el armado del welcome podrían solaparse.

**Archivos afectados**:
- `core/orchestrator.py` — `_handle_nif_and_welcome`
- `services/zoa_client.py` — las funciones de búsqueda y envío

**Implementación**:
```python
import asyncio
# O más simple con concurrent.futures:
from concurrent.futures import ThreadPoolExecutor

# Ejecutar búsqueda de contacto y preparación en paralelo
with ThreadPoolExecutor(max_workers=2) as executor:
    future_contact = executor.submit(search_contact_by_phone, wa_id, company_id)
    # Mientras tanto, preparar la sesión y el welcome template
    # ...
    contact_response = future_contact.result(timeout=5)
```

**Impacto estimado**: Ahorro de 200-500ms en el primer mensaje de cada conversación.

**Riesgo**: Bajo. Solo afecta al primer mensaje. Si la búsqueda falla, el fallback ya existe (pedir NIF manualmente).

---

### 5. Cache de pólizas ERP en memoria de sesión

**Problema**: `erp_get_policies` tarda entre 760ms y 6.7s (L3, L14, L15). Si el usuario consulta su póliza y luego pide un documento de la misma, se vuelve a llamar al ERP para obtener las pólizas.

**Archivos afectados**:
- `tools/erp/erp_tools.py` — las funciones tool que llaman al ERP
- `core/memory_schema.py` — para definir la estructura de cache en la sesión

**Implementación**: Cuando un tool obtiene pólizas del ERP, guardar el resultado simplificado en `session["agent_memory"]["global"]["cached_policies"]` con un TTL. Antes de llamar al ERP, verificar si hay cache válida.

```python
# En el tool de get_policies
cached = memory.get("global", {}).get("cached_policies")
if cached and cached.get("nif") == nif:
    return cached["data"]

# Si no hay cache, llamar al ERP y guardar
result = erp.get_policies(nif)
# Guardar en memoria para uso futuro en la misma sesión
```

**Impacto estimado**: Elimina 1-7s en requests subsecuentes que necesitan datos de pólizas ya consultadas.

**Riesgo**: Bajo. El cache es por sesión (no persiste entre conversaciones). Si los datos cambian durante la conversación (poco probable), el usuario puede reiniciar la sesión.

---

## Priorización

| # | Acción | Impacto | Esfuerzo | Prioridad |
|---|--------|---------|----------|-----------|
| 1 | Modelo ligero para classifiers | **Alto** (-10-20s en cadenas) | Bajo (cambiar import en 3 archivos + 1 función nueva) | **P0** |
| 3 | Eliminar `generic_knowledge_agent` intermedio | **Alto** (-10s por request afectado) | Bajo (auditoría + ajuste de routing) | **P0** |
| 2 | Consolidar saves a Postgres | **Medio** (-600-800ms) | Medio (refactorizar orchestrator) | **P1** |
| 5 | Cache de pólizas ERP | **Medio-Alto** (-1-7s en requests subsecuentes) | Medio (lógica de cache en tools) | **P1** |
| 4 | Paralelizar NIF + Welcome | **Bajo** (-200-500ms solo en primer mensaje) | Bajo-Medio (threading) | **P2** |

## KPIs objetivo post-optimización

| Métrica | Actual | Objetivo |
|---------|--------|----------|
| Latencia media por request | ~10s | < 5s |
| Latencia P95 | ~38s | < 12s |
| Classifiers (LLM time) | 3-14s | < 2s |
| Postgres total por request | ~350ms | < 200ms |
| Cadenas con `generic_knowledge_agent` intermedio | ~12% requests | 0% |
