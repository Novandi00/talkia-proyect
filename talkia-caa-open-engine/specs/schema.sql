-- TalKIA (caa-open-engine) - Formal SQLite3 Schema v2.0 (Core LAMP + Fringe + ARASAAC Cache)
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;

CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    trigger_type TEXT NOT NULL CHECK (
        trigger_type IN ('saludo', 'despedida', 'necesidades', 'emociones', 'asistencia', 'conversacion')
    ),
    conversation_intent TEXT NULL CHECK (
        conversation_intent IS NULL OR conversation_intent IN ('pregunta', 'afirmacion', 'respuesta', 'topico_libre')
    ),
    scenario TEXT NOT NULL DEFAULT 'general' CHECK (
        scenario IN ('general', 'casa', 'escuela', 'calle', 'salud')
    ),
    hour_bucket INTEGER NOT NULL CHECK (hour_bucket >= 0 AND hour_bucket <= 23),
    interlocutor_context TEXT NULL CHECK (interlocutor_context IS NULL OR length(interlocutor_context) <= 200),
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    final_phrase TEXT NULL CHECK (final_phrase IS NULL OR length(final_phrase) <= 240),
    committed INTEGER NOT NULL DEFAULT 0 CHECK (committed IN (0, 1)),
    idempotency_key TEXT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS interaction_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    step_index INTEGER NOT NULL CHECK (step_index >= 0),
    word_source TEXT NOT NULL DEFAULT 'fringe' CHECK (word_source IN ('core', 'fringe')),
    context_path TEXT NOT NULL,
    suggested_words TEXT NOT NULL,
    selected_word TEXT NULL,
    latency_ms INTEGER NOT NULL DEFAULT 0 CHECK (latency_ms >= 0),
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS bayesian_priors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trigger_type TEXT NOT NULL CHECK (
        trigger_type IN ('saludo', 'despedida', 'necesidades', 'emociones', 'asistencia', 'conversacion')
    ),
    conversation_intent TEXT NOT NULL DEFAULT 'general',
    scenario TEXT NOT NULL DEFAULT 'general' CHECK (
        scenario IN ('general', 'casa', 'escuela', 'calle', 'salud')
    ),
    hour_bucket INTEGER NOT NULL CHECK (hour_bucket >= -1 AND hour_bucket <= 23),
    prev_word TEXT NOT NULL DEFAULT '__START__',
    candidate_word TEXT NOT NULL CHECK (length(candidate_word) >= 1 AND length(candidate_word) <= 32),
    frequency INTEGER NOT NULL DEFAULT 1 CHECK (frequency >= 0),
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(trigger_type, conversation_intent, scenario, hour_bucket, prev_word, candidate_word)
);

CREATE TABLE IF NOT EXISTS core_vocabulary (
    slot_id INTEGER PRIMARY KEY CHECK (slot_id >= 0 AND slot_id < 12),
    row_idx INTEGER NOT NULL CHECK (row_idx >= 0 AND row_idx < 2),
    col_idx INTEGER NOT NULL CHECK (col_idx >= 0 AND col_idx < 6),
    word TEXT NOT NULL UNIQUE CHECK (length(word) >= 1 AND length(word) <= 24),
    label TEXT NOT NULL,
    fitzgerald_category TEXT NOT NULL CHECK (
        fitzgerald_category IN ('pronoun', 'verb', 'noun', 'adjective', 'social', 'question', 'negation')
    ),
    arasaac_id INTEGER NULL,
    UNIQUE(row_idx, col_idx)
);

CREATE TABLE IF NOT EXISTS pictogram_cache (
    normalized_key TEXT PRIMARY KEY,
    surface_word TEXT NOT NULL,
    lemma TEXT NOT NULL,
    arasaac_id INTEGER NULL,
    source TEXT NOT NULL CHECK (source IN ('arasaac', 'mulberry', 'local_svg')),
    fitzgerald_category TEXT NOT NULL CHECK (
        fitzgerald_category IN ('pronoun', 'verb', 'noun', 'adjective', 'social', 'question', 'negation', 'misc')
    ),
    image_url TEXT NULL,
    inline_svg TEXT NULL,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_sessions_lookup
    ON sessions (trigger_type, scenario, hour_bucket, committed);

CREATE INDEX IF NOT EXISTS idx_logs_session_step
    ON interaction_logs (session_id, step_index DESC);

CREATE INDEX IF NOT EXISTS idx_priors_context_lookup
    ON bayesian_priors (trigger_type, conversation_intent, scenario, hour_bucket, prev_word, frequency DESC);
