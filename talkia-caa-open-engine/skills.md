---
name: talkia-caa-orchestrator
description: Spec-Driven Development (SDD) skill and operational rules for building, auditing, and extending the TalKIA (caa-open-engine) Augmentative and Alternative Communication platform.
version: 1.1.0
---

# TalKIA (`caa-open-engine`) — Agent Skills & Operational Rules (`skills.md`)

Este archivo define las capacidades, invariantes matemáticas y reglas de diseño que cualquier agente orquestador (**Antigravity**, **Codex**, **Claude Code**, **Cursor**) debe respetar al ejecutar o expandir el repositorio.

## 1. Invariantes del Dominio (Reglas Inquebrantables)
1. **Spec-First (Verdad Única en `specs/`)**:
   - Ningún endpoint de `backend/` ni componente de `frontend/` puede agregar o renombrar atributos fuera de `specs/schema.sql`, `specs/llm_contract.json` y `specs/openapi.yaml`.
2. **Cardinalidad Exacta de Selección (`10 candidate_words`)**:
   - En cada paso de la máquina de estados (Nivel 2, Nivel 3 o bucle abierto en `conversacion`), el motor SIEMPRE debe devolver exactamente **10 palabras únicas** (`minItems: 10`, `maxItems: 10`, `uniqueItems: true`).
3. **Los 6 Triggers de Nivel 1**:
   - Triggers deterministas: `saludo`, `despedida`, `necesidades`, `emociones`, `asistencia`.
   - Trigger de estado abierto: `conversacion`, que habilita 4 sub-intenciones dinámicas (`pregunta`, `afirmacion`, `respuesta`, `topico_libre`) para sostener diálogos bidireccionales.
4. **Motor Híbrido Bayesiano + LLM con Fallback Determinista**:
   - La probabilidad de cada palabra candidata se modela como:
     $$P(W_n \mid \text{Trigger}, \text{Intent}, \text{HourBucket}, W_{n-1}) = \alpha \cdot P_{\text{SQLite}}(W_n \mid C) + (1 - \alpha) \cdot P_{\text{LLM}}(W_n \mid C)$$
   - Si el LLM excede el presupuesto de latencia (600 ms) o falla la validación de JSON Schema, el motor **debe degradar limpiamente (Zero-Crash Fallback)** al Prior Bayesiano en SQLite con suavizado de Laplace.

## 2. Skills por Rol de Agente (Software Factory)

### Skill A: `spec-architect` (Iteración 0)
- **Responsabilidad**: Mantener la coherencia entre SQLite, JSON Schema Draft-07 y OpenAPI 3.1.0.
- **Validación**: Verificar que todos los `CHECK` constraints de SQLite coincidan exactamente con los `enum` de OpenAPI y JSON Schema.

### Skill B: `bayesian-backend-engineer` (Iteración 1 y 2)
- **Responsabilidad**: Implementar el cálculo de frecuencias condicionales en SQLite (`backend/bayesian_engine.py`) y la fusión con inferencia estructurada (`backend/llm_client.py`).
- **Regla de Oro**: Cuando el usuario confirma una oración (`POST /session/commit`), incrementar los conteos bigrama `(prev_word -> selected_word)` en `bayesian_priors` dentro de una transacción atómica.

### Skill C: `accessible-ui-builder` (Iteración 3)
- **Responsabilidad**: Mantener la interfaz CAA en `frontend/` con alto contraste (WCAG AAA), áreas táctiles mínimas de `64x64px`, cero distracciones visuales, conmutador rápido de sub-intenciones en el nodo `conversacion` (`¿Pregunta?`, `Afirmación`, `Respuesta`, `Tema Libre`) y síntesis de voz (TTS) instantánea en español (`es-AR` / `es-ES`).

### Skill D: `bayesian-critic-qa` (Auditoría Continua)
- **Responsabilidad**: Ejecutar `python3 backend/test_engine.py` tras cada cambio para comprobar:
  1. Integridad referencial en SQLite.
  2. Cumplimiento estricto de `llm_contract.json` (10 palabras únicas, sin duplicados, primera persona singular en `constructed_sentence`).
  3. Latencia P95 bajo 50 ms en modo offline/prior y bajo 600 ms en modo híbrido.
