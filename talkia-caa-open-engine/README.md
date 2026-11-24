# TalKIA (`caa-open-engine`) — Spec-Driven Hybrid CAA Platform

Motor abierto de **Comunicación Aumentativa y Alternativa (CAA)** diseñado bajo el paradigma **Spec-Driven Development (SDD)** para ejecución autónoma en agentes orquestadores (**Antigravity**, **Codex**, **Claude Code**, **Cursor**).

## Arquitectura y Nodos de Nivel 1 (6 Triggers)
1. `saludo` — Aperturas sociales contextualizadas por hora del día (`hour_bucket`).
2. `despedida` — Cierres de interacción rápidos.
3. `necesidades` — Solicitudes fisiológicas y de confort prioritario.
4. `emociones` — Expresión de estados afectivos y ánimo.
5. `asistencia` — Pedidos de ayuda física o ambiental inmediata.
6. `conversacion` *(Nuevo Nodo de Estado Abierto)* — Sostiene diálogos dinámicos mediante 4 sub-intenciones:
   - `pregunta`: Apertura y construcción de preguntas (`¿Qué...?`, `¿Cómo...?`, `¿Cuándo...?`).
   - `afirmacion`: Opiniones, relatos y juicios en primera persona (`Yo pienso...`, `Me encantó...`).
   - `respuesta`: Respuestas ágiles al interlocutor (`Sí, por supuesto`, `Todavía no`, `Depende`).
   - `topico_libre`: Propuesta de temas de charla (`Hablemos de música`, `Contame cómo te fue`).

## Estructura del Paquete
- `specs/schema.sql`: Esquema formal SQLite3 con tablas `sessions`, `interaction_logs` y `bayesian_priors`.
- `specs/llm_contract.json`: Contrato JSON Schema Draft-07 con invariante de exactamente 10 `candidate_words` únicas.
- `specs/openapi.yaml`: Especificación OpenAPI 3.1.0 (`/session/start`, `/session/step`, `/session/commit`).
- `next.json`: Pipeline de ejecución por iteraciones (0 a 3), configuración de triggers y checklist de contexto faltante para agentes orquestadores.
- `skills.md`: Reglas operativas y skills por rol para el agente constructor y el crítico bayesiano.
- `prompts/ITERATIONS_SDD.md`: Prompts completos de Ejecución y Auditoría (Iteraciones 0 a 3).
- `backend/`: Motor Bayesiano con suavizado de Laplace (`bayesian_engine.py`), validador de contrato (`models.py`), cliente híbrido (`llm_client.py`), servidor HTTP (`main.py`) y suite de auditoría (`test_engine.py`).
- `dataset/`: Corpus semilla en español rioplatense (`seed_priors.json`) e inicializador (`seed_db.py`).
- `frontend/`: Interfaz web CAA accesible (`index.html`, `styles.css`, `app.js`) con soporte TTS.

## Ejecución Rápida
```bash
# 1. Inicializar base SQLite y correr la suite de verificación del Crítico Bayesiano
python3 backend/test_engine.py

# 2. Levantar el backend en http://localhost:8000
python3 -m backend.main

# 3. Abrir el frontend en http://localhost:3000
python3 -m http.server 3000 --directory frontend
```
