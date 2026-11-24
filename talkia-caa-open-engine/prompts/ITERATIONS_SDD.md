# Arquitectura Multi-Agente TalKIA (`caa-open-engine`) — Prompts de Ejecución y Auditoría (Iteraciones 0 a 3)

Este documento contiene los prompts listos para copiar o ejecutar secuencialmente en tu orquestador (**Antigravity** / **Codex**).

---

## Iteración 0: El Arquitecto de Contratos (Spec-Freeze)
**Objetivo:** Congelar la verdad matemática y estructural en `specs/` incluyendo el 6to trigger `conversacion` (preguntas, afirmaciones, respuestas y tópicos libres).

### 0.1 Prompt de Ejecución (Agente 0 - Spec Architect)
> Valida y mantén sincronizados `specs/schema.sql`, `specs/llm_contract.json` y `specs/openapi.yaml`. Asegura que `trigger_type` incluya `('saludo', 'despedida', 'necesidades', 'emociones', 'asistencia', 'conversacion')` y que `conversation_mode` soporte `('estandar', 'pregunta', 'afirmacion', 'respuesta', 'topico_libre')`.

### 0.2 Prompt de Auditoría (Crítico 0)
> Verifica que `llm_contract.json` imponga `additionalProperties: false`, `minItems: 10`, `maxItems: 10`, `uniqueItems: true` en `candidate_words`, y que los índices de `schema.sql` cubran `(trigger_type, conversation_intent, hour_bucket, prev_word, frequency DESC)`.

---

## Iteración 1: El Ingeniero de Motor Bayesiano y Persistencia (SQLite + Priors)
**Objetivo:** Construir el motor probabilístico local que aprende de cada selección del usuario y garantiza respuesta en `<15ms` incluso sin conexión a internet.

### 1.1 Prompt de Ejecución (Agente 1 - Bayesian Engine Builder)
> Implementa `backend/db.py`, `backend/bayesian_engine.py` y `dataset/seed_db.py`. Calcula $P(W_n \mid \text{Trigger}, \text{Intent}, \text{HourBucket}, W_{n-1})$ combinando el bucket horario exacto (`hour_bucket`) con el prior global (`hour_bucket = -1`) mediante suavizado de Laplace. En el nodo `conversacion`, filtra o prioriza aperturas interrogativas (`¿Qué`, `¿Cómo`, `¿Cuándo`, `¿Dónde`, `¿Por qué`, `¿Puedo`) cuando `conversation_intent == 'pregunta'`, y aperturas declarativas (`Yo pienso`, `Me gusta`, `Quiero contarte`, `Creo que`, `Hoy hice`) cuando `conversation_intent == 'afirmacion'`.

### 1.2 Prompt de Auditoría (Crítico 1)
> Ejecuta `dataset/seed_db.py` y comprueba que para cualquier combinación de los 6 triggers, 4 sub-intenciones de conversación y 24 horas del día, el motor devuelva siempre 10 palabras candidatas únicas y gramaticalmente coherentes.

---

## Iteración 2: El Integrador de Inferencia Restringida y API (FastAPI / WSGI)
**Objetivo:** Exponer los contratos de `specs/openapi.yaml` y fusionar el Prior Bayesiano con un LLM estructurado (Gemini / OpenAI / Local) validado contra `specs/llm_contract.json`.

### 2.1 Prompt de Ejecución (Agente 2 - API & LLM Integrator)
> Implementa `backend/models.py`, `backend/llm_client.py` y `backend/main.py`. El cliente LLM debe recibir el camino contextual (`context_path`), el `trigger_type`, el `conversation_intent` y el Top-15 del Prior Bayesiano como ancla empírica, devolviendo un JSON estricto que cumpla `specs/llm_contract.json`. Si no hay API key configurada o el proveedor tarda más de 600 ms, devuelve de forma transparente la predicción del motor Bayesiano local.

### 2.2 Prompt de Auditoría (Crítico 2)
> Ejecuta pruebas de contrato sobre `POST /session/start`, `POST /session/step` y `POST /session/commit`. Verifica que ninguna respuesta viole el esquema JSON Draft-07.

---

## Iteración 3: El Constructor de Interfaz CAA Accesible (Frontend + TTS)
**Objetivo:** Interfaz web de alta velocidad, accesible y de bajo esfuerzo cognitivo/motor.

### 3.1 Prompt de Ejecución (Agente 3 - Accessible UI Builder)
> Construye `frontend/index.html`, `frontend/styles.css` y `frontend/app.js`. Muestra los 6 nodos de Nivel 1 (incluyendo el nodo destacado **Conversación** con selectores rápidos de *Pregunta*, *Afirmación*, *Respuesta* y *Tópico Libre*), una grilla de 10 palabras candidatas con botones amplios de alto contraste, barra de oración construida en tiempo real y botón de locución TTS (`window.speechSynthesis`) con registro automático de latencia (`latency_ms`).
