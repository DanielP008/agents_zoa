# Plan de Reducción de Latencia — ZOA Agents

> Última actualización: 2026-02-09 — Post battery test (60 cases, 541 requests traced)

---

## Diagnóstico actualizado con datos reales

### KPIs actuales vs objetivo

| Métrica | Actual | Target | Compliance |
|---------|--------|--------|------------|
| **Total ms** | 8,575ms | 2,700ms | 56.9% |
| **Postgres ms** | 274ms | 200ms | 45.3% |
| **Agent LLM ms** | 7,375ms | 1,000ms | 51.4% |
| **ERP ms** | 36ms | 500ms | 72.1% ✅ |
| **ZOA ms** | 437ms | 500ms | 96.9% ✅ |

### Hallazgo crítico: gemini-2.5-flash colapsa bajo carga

| Modelo | Avg LLM ms | Comportamiento bajo carga |
|--------|-----------|---------------------------|
| **gemini-3-flash-preview** | 4,004ms | Estable, consistente 2-5s |
| **gemini-2.5-flash** | **31,148ms** | 1-2s idle → **234,000-244,000ms bajo carga** |

Evidencia directa del `request_trace.jsonl`:
- `classifier_siniestros_decision` (gemini-2.5-flash): **234,743ms** — casi 4 minutos
- `classifier_siniestros_decision` (gemini-2.5-flash): **240,747ms** — 4 minutos
- `classifier_gestion_decision` (gemini-2.5-flash): **235,551ms** — 4 minutos
- Todos estos son la causa de los 14/60 test cases fallidos por timeout

**Conclusión**: gemini-2.5-flash tiene "thinking" que es impredecible. Bajo concurrencia, el API de Google lo throttlea o el modelo "piensa" excesivamente, multiplicando la latencia x200.

### Distribución de latencia por componente (requests normales)

| Componente | Tiempo medio | % del total |
|------------|-------------|-------------|
| **Agent LLM** | ~7.4s | ~86% |
| **Postgres** | ~274ms | ~3.2% |
| **Tool calls (ERP+ZOA)** | ~473ms | ~5.5% |
| **Overhead** | ~454ms | ~5.3% |

### Latencia por agente (datos battery test, 541 requests)

| Agente | Modelo | Avg ms | Notas |
|--------|--------|--------|-------|
| `receptionist_decision` | gemini-3-flash-preview | 2,500-5,000ms | Estable |
| `classifier_siniestros_decision` | gemini-2.5-flash | 1,200-**240,000ms** | CRÍTICO |
| `classifier_gestion_decision` | gemini-2.5-flash | 900-**235,000ms** | CRÍTICO |
| `apertura_siniestro_agent` | gemini-3-flash-preview | 4,000-8,000ms | OK |
| `modificar_poliza_agent` | gemini-3-flash-preview | 2,000-6,000ms | OK |
| `consultar_poliza_agent` | gemini-3-flash-preview | 3,000-7,000ms | OK |
| `devolucion_agent` | gemini-3-flash-preview | 4,000-9,000ms | OK |

### Postgres: demasiados round-trips en cadenas de routing

Requests con routing chain (receptionist → classifier → specialist) generan **11 postgres calls** (~700ms):
```
get_session → get_session → save_session → get_session → save_session → 
get_session → save_session → get_session → save_session → get_session → save_session
```
Requests directos al especialista solo generan **3 calls** (~170ms).

### Bug: Classifier stuck en loop

Caso "Incendio garaje" (APE003): el `classifier_siniestros_agent` respondió 5 veces consecutivas "Te pongo en contacto con un especialista..." sin nunca ejecutar el route. El classifier devuelve mensaje de routing pero la acción no se ejecuta.

---

## Plan de acción (priorizado por impacto y datos)

### 🔴 P0-A: Reemplazar gemini-2.5-flash (CRÍTICO)

**Problema**: gemini-2.5-flash es el cuello de botella #1. Bajo carga concurrente va de 1s a 240s.

**Opciones**:

| Opción | Avg esperado | Pro | Contra |
|--------|-------------|-----|--------|
| **gemini-2.0-flash** | ~1-2s | Mismo ecosistema, sin "thinking", rápido | Menos inteligente |
| **gemini-3-flash-preview** | ~3-4s | Ya probado y estable (receptionist lo usa) | Más lento que 2.0 |
| **gpt-4.1-mini** | ~1-2s | Muy rápido, bueno en structured output | Requiere OpenAI key |

**Recomendación**: Usar **gemini-2.0-flash** como default. No tiene "thinking" → latencia predecible.

**Archivos a modificar**:
- `.env` → cambiar `GEMINI_MODEL_FAST=gemini-2.0-flash`
- O si se prefiere OpenAI: `.env` → `FAST_LLM_PROVIDER=openai`, `OPENAI_MODEL_FAST=gpt-4.1-mini`

**Impacto estimado**: Classifiers de **31,148ms avg → ~1,500ms avg**. Eliminación total de los timeouts de 240s.

---

### 🔴 P0-B: Fix classifier routing loop bug

**Problema**: El classifier devuelve `needs_more_info=false` con un `question` de routing ("te pongo en contacto...") pero no ejecuta el route real. Queda en loop respondiendo lo mismo.

**Diagnóstico necesario**: Revisar en `classifier_agent.py` qué condición causa que el classifier envíe un mensaje sin ejecutar la redirección. Posible que `decision.route` sea null o no matchee la allowlist.

**Archivos afectados**:
- `agents/domains/siniestros/classifier_agent.py`
- `agents/domains/gestion/classifier_agent.py`
- `agents/domains/ventas/classifier_agent.py`

**Impacto**: Elimina loops infinitos que consumen recursos y dan timeout.

---

### 🟡 P1-A: Reducir round-trips a Postgres

**Problema**: En cadenas de routing (receptionist → classifier → specialist), se ejecutan **11 postgres calls** (~700ms). En requests directos solo 3 (~170ms).

Cada paso del routing loop hace:
```python
set_target_agent()    # get_session + save_session = 2 calls
update_agent_memory() # get_session + save_session = 2 calls
# = 4 calls por paso × 3 pasos = 12 calls
```

**Implementación**: Acumular cambios en memoria y hacer un solo `save_session` al final.

```python
# ANTES (orchestrator routing loop): 11 calls, ~700ms
session_manager.set_target_agent(...)    # get + save
session_manager.update_agent_memory(...) # get + save

# DESPUÉS: 3 calls, ~180ms
session["target_agent"] = new_target
session["domain"] = new_domain
session["agent_memory"] = memory
# save_session() solo al final del routing
```

**Archivos afectados**: `core/orchestrator.py`, `core/db.py`

**Impacto estimado**: -520ms en requests con cadenas de routing (700ms → 180ms).

---

### 🟡 P1-B: Receptionist usa modelo demasiado pesado

**Problema**: `receptionist_decision` usa `gemini-3-flash-preview` (avg 3,000-5,000ms). El receptionist solo clasifica en 3 dominios (siniestros/gestión/ventas) con structured output. No necesita el modelo completo.

**Implementación**: Cambiar receptionist a `get_llm_fast()` en vez de `get_llm()`.

**Archivos afectados**: `agents/receptionist_agent.py`

**Impacto estimado**: Receptionist de ~4,000ms → ~1,500ms. Como TODOS los requests pasan por el receptionist, esto impacta el 100% del tráfico.

> NOTA: Verificar primero si el receptionist ya usa `get_llm_fast()` (se cambió anteriormente pero puede haber regresado).

---

### 🟡 P1-C: Cache de pólizas ERP en sesión

**Problema**: `erp_get_policies` tarda ~740ms. Se llama múltiples veces en la misma sesión (el especialista consulta pólizas, luego las vuelve a pedir para modificar/consultar detalles).

**Implementación**: Guardar resultado de `erp_get_policies` en `session["agent_memory"]["global"]["cached_policies"]`. Verificar cache antes de llamar al ERP.

**Archivos afectados**: `tools/erp/erp_tools.py`, `core/memory_schema.py`

**Impacto estimado**: -740ms en cada llamada ERP subsecuente dentro de la misma sesión.

---

### 🟢 P2-A: Paralelizar NIF lookup + Welcome

**Problema**: En `_handle_nif_and_welcome`, la búsqueda de contacto por teléfono y el welcome se ejecutan secuencialmente.

**Impacto estimado**: -200-500ms solo en el primer mensaje.

---

### 🟢 P2-B: Timeout y retry inteligente para LLM

**Problema**: No hay timeout en las llamadas LLM. Si gemini-2.5-flash se cuelga 4 minutos, el request espera 4 minutos.

**Implementación**: Agregar `timeout` a las llamadas LLM y retry con backoff.

```python
# En get_gemini_fast / get_llm
return ChatGoogleGenerativeAI(
    model=model,
    google_api_key=api_key,
    temperature=0.1,
    max_retries=2,
    timeout=15,  # NUEVO: máximo 15s por llamada
)
```

**Impacto**: Previene requests de 240s. Falla rápido y permite retry.

---

## Roadmap de implementación

| Fase | Acciones | Impacto total estimado | Esfuerzo |
|------|----------|----------------------|----------|
| **Fase 1** (inmediato) | P0-A: Cambiar modelo classifiers + P0-B: Fix routing loop | **-29,000ms avg en classifiers** | 30 min |
| **Fase 2** (día siguiente) | P1-A: Consolidar Postgres + P1-B: Receptionist fast | **-3,500ms en cadenas routing** | 2-3 hrs |
| **Fase 3** (semana) | P1-C: Cache ERP + P2-A: Parallelizar NIF + P2-B: Timeouts | **-1,200ms adicionales** | 3-4 hrs |

## KPIs objetivo post-optimización

| Métrica | Actual | Post-Fase 1 | Post-Fase 3 | Target |
|---------|--------|-------------|-------------|--------|
| **Total avg** | 8,575ms | ~3,500ms | **~2,500ms** | 2,700ms |
| **P95** | 15,034ms | ~8,000ms | **~5,000ms** | — |
| **Max** | 244,682ms | ~15,000ms | **~10,000ms** | — |
| **Classifier avg** | 31,148ms | ~1,500ms | ~1,500ms | 1,000ms |
| **Receptionist avg** | 4,004ms | 4,004ms | **~1,500ms** | 1,000ms |
| **Postgres avg** | 274ms | 274ms | **~150ms** | 200ms |
| **Compliance rate** | 56.9% | ~75% | **~90%** | 100% |

## Decisiones ya tomadas

- [x] Classifiers usan `get_llm_fast()` — implementado
- [x] Sistema de timing con modelo por agente — implementado
- [x] Battery test con 60 use cases — implementado
- [x] Dashboard de latencia con métricas por modelo — implementado
- [x] Soporte dual OpenAI/Gemini en `llm.py` — implementado
- [x] `end_chat` en classifiers — implementado
- [ ] **PENDIENTE**: Cambiar gemini-2.5-flash por modelo estable
- [ ] **PENDIENTE**: Fix routing loop en classifiers
- [ ] **PENDIENTE**: Consolidar Postgres saves
- [ ] **PENDIENTE**: Cache ERP
- [ ] **PENDIENTE**: Timeouts en LLM calls
