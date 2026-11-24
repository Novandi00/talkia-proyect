<div align="center">
  <img src="talkia-caa-open-engine/frontend/logo.svg" alt="TalKIA Logo" width="130" height="130" />
  <h1>TalKIA — caa-open-engine v2.0</h1>
  <p><strong>Motor Abierto de Comunicación Aumentativa y Alternativa (CAA)</strong></p>
  <p>Arquitectura Híbrida Offline-First · Principio LAMP (Core Fijo) · Vocabulario Periférico (Fringe Contextual) · ARASAAC & Piper WASM</p>

  <p>
    <img src="https://img.shields.io/badge/License-MIT-blue.svg" alt="License" />
    <img src="https://img.shields.io/badge/Status-Spec--Frozen%20v2.0-success" alt="Status" />
    <img src="https://img.shields.io/badge/Accessibility-WCAG%20AAA-purple" alt="Accessibility" />
    <img src="https://img.shields.io/badge/Offline--First-IndexedDB%20%2B%20SQLite%20WAL-orange" alt="Offline" />
    <img src="https://img.shields.io/badge/Symbols-ARASAAC%20Enabled-teal" alt="ARASAAC" />
  </p>
</div>

---

## 🌟 Características Principales

TalKIA es una plataforma CAA de código abierto pensada para personas dentro del espectro autista y con desafíos en la comunicación verbal:

- 🧠 **Arquitectura Core + Fringe (Principio LAMP):** Tablero de 12 palabras núcleo (*Core*) con posiciones espaciales fijas e inmutables para consolidación de memoria motora, complementado con 10 palabras periféricas dinámicas (*Fringe*).
- 🎨 **Clave de Color Fitzgerald Key:** Codificación cromática morfosintáctica configurable (Pronombres en amarillo, Verbos en verde, Sustantivos en naranja, Emociones en azul, Social en rosa, Preguntas en violeta y Negación en rojo).
- 🌿 **Modo de Baja Carga Sensorial:** Diseñado sin animaciones bruscas, con tipografía clara y contrastes descansados para prevenir sobrecarga cognitiva (inspirado en *ekyaaa/talkie-helpie*).
- 🖼️ **Integración Nativa ARASAAC:** Resolución y renderizado de pictogramas estandarizados con caché multinivel (<50ms) y lematizador en español rioplatense.
- 🔊 **TTS Resiliente Offline-First:** Abstracción `TTSProvider` con soporte para inferencia local neuronal (Piper WASM) y degradación fluida a Web Speech API (`es-AR`).
- ⚡ **Backend Defensivo y Multi-Hilo:** Python 3.12 `ThreadingHTTPServer` con SQLite WAL concurrente, protección de memoria (tope 16KB), transacciones atómicas e idempotencia estricta contra envenenamiento de priors.

---

## 📂 Estructura del Repositorio

```text
talkia-proyect/
├── plan01.md                       # Plan maestro de ingeniería v2.0 y arquitectura
├── talkia-caa-open-engine/
│   ├── backend/
│   │   ├── main.py                 # Servidor ThreadingHTTPServer con telemetría y CORS
│   │   ├── repository.py           # Repositorio SQLite WAL concurrente e idempotente
│   │   ├── core_fringe_engine.py   # Motor probabilístico con Laplace y guard de LLM
│   │   ├── pictogram_service.py    # Servicio de resolución de símbolos ARASAAC y SVG
│   │   ├── schemas.py              # Validación estricta fail-fast
│   │   └── test_engine.py          # Suite de verificación y benchmark P95 < 50ms
│   ├── frontend/
│   │   ├── index.html              # Tablero interactivo accesible y responsivo
│   │   ├── styles.css              # Estilos estéticos con Fitzgerald Key y modo sensorial
│   │   ├── app.js                  # Controlador frontend con persistencia y fallback
│   │   ├── tts_provider.js         # Abstracción de síntesis de voz offline
│   │   ├── offline_store.js        # Persistencia en IndexedDB
│   │   ├── contracts.js            # Validación en cliente
│   │   ├── logo.svg                # Isologo oficial TalKIA
│   │   └── sw.js                   # Service Worker Cache-First para PWA
│   ├── dataset/
│   │   ├── seed_priors.json        # Corpus semilla en español
│   │   └── seed_db.py              # Inicializador de la base de datos
│   └── specs/
│       ├── schema.sql              # Esquema SQLite v2.0
│       ├── llm_contract.json       # Contrato JSON Schema Draft-07
│       └── openapi.yaml            # Especificación OpenAPI 3.1.0
└── .gitignore                      # Exclusiones de binarios y cachés
```

---

## 🚀 Inicio Rápido

### 1. Ejecutar las Pruebas Automatizadas
```bash
python3 talkia-caa-open-engine/backend/test_engine.py
```

### 2. Iniciar el Servidor Backend
```bash
python3 -m backend.main
# Escuchando en http://localhost:8000
```

### 3. Servir la Aplicación Frontend
```bash
python3 -m http.server 3000 --directory talkia-caa-open-engine/frontend
# Abrir en el navegador: http://localhost:3000
```

---

## 📄 Licencia

Este proyecto es software libre bajo licencia **MIT**.  
Los pictogramas son propiedad de **ARASAAC** (Gobierno de Aragón) publicados bajo licencia **Creative Commons (BY-NC-SA)**.
