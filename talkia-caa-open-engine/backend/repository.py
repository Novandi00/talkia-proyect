"""backend/repository.py — Repositorio SQLite WAL Concurrente e Idempotente (< 5ms)."""
from __future__ import annotations

from contextlib import contextmanager
import json
import os
import sqlite3
import threading
from typing import Any, Dict, Iterable, List, Optional, Tuple

from backend.schemas import PictogramMetadata

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCHEMA_PATH = os.path.join(BASE_DIR, "specs", "schema.sql")
_INIT_LOCK = threading.Lock()
_INITIALIZED_PATHS: set[str] = set()

# 12 palabras Core con coordenadas LAMP inmutables (2 filas x 6 columnas)
DEFAULT_CORE_LAMP: List[Tuple[int, int, int, str, str, str, int]] = [
    (0, 0, 0, "yo", "Yo", "pronoun", 31807),
    (1, 0, 1, "vos", "Vos", "pronoun", 12264),
    (2, 0, 2, "quiero", "Quiero", "verb", 5441),
    (3, 0, 3, "necesito", "Necesito", "verb", 37160),
    (4, 0, 4, "ir", "Ir", "verb", 2432),
    (5, 0, 5, "ayuda", "Ayuda", "social", 32648),
    (6, 1, 0, "sí", "Sí", "social", 5584),
    (7, 1, 1, "no", "No", "negation", 5526),
    (8, 1, 2, "más", "Más", "adjective", 5508),
    (9, 1, 3, "parar", "Parar", "negation", 7196),
    (10, 1, 4, "me_gusta", "Me gusta", "verb", 37815),
    (11, 1, 5, "ahora", "Ahora", "adjective", 32747),
]


def resolve_db_path(explicit_path: Optional[str] = None) -> str:
    return explicit_path or os.environ.get(
        "TALKIA_DB_PATH", os.path.join(BASE_DIR, "backend", "talkia_caa.sqlite3")
    )


class TalkiaRepository:
    """Acceso a datos desacoplado con garantías ACID, WAL y prevención de Data Poisoning."""

    def __init__(self, db_path: Optional[str] = None) -> None:
        self.db_path = resolve_db_path(db_path)
        self._ensure_ready()

    def _ensure_ready(self) -> None:
        if self.db_path in _INITIALIZED_PATHS and os.path.exists(self.db_path):
            return
        with _INIT_LOCK:
            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
            with sqlite3.connect(self.db_path, timeout=5.0) as conn:
                with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
                    conn.executescript(f.read())
                conn.executemany(
                    """
                    INSERT INTO core_vocabulary
                        (slot_id, row_idx, col_idx, word, label, fitzgerald_category, arasaac_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(slot_id) DO NOTHING
                    """,
                    DEFAULT_CORE_LAMP,
                )
                conn.commit()
            _INITIALIZED_PATHS.add(self.db_path)

    @contextmanager
    def connection(self):
        conn = sqlite3.connect(self.db_path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        conn.execute("PRAGMA busy_timeout = 5000;")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def get_core_vocabulary(self) -> List[Dict[str, Any]]:
        with self.connection() as conn:
            rows = conn.execute(
                """
                SELECT slot_id, row_idx, col_idx, word, label, fitzgerald_category, arasaac_id
                FROM core_vocabulary
                ORDER BY row_idx ASC, col_idx ASC
                """
            ).fetchall()
            return [dict(r) for r in rows]

    def create_session_with_initial_log(
        self,
        session_id: str,
        trigger_type: str,
        conversation_intent: Optional[str],
        scenario: str,
        hour_bucket: int,
        interlocutor_context: Optional[str],
        suggested_words: List[str],
    ) -> None:
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO sessions
                    (id, trigger_type, conversation_intent, scenario, hour_bucket, interlocutor_context, committed)
                VALUES (?, ?, ?, ?, ?, ?, 0)
                """,
                (session_id, trigger_type, conversation_intent, scenario, hour_bucket, interlocutor_context),
            )
            conn.execute(
                """
                INSERT INTO interaction_logs
                    (session_id, step_index, word_source, context_path, suggested_words, selected_word, latency_ms)
                VALUES (?, 0, 'fringe', '[]', ?, NULL, 0)
                """,
                (session_id, json.dumps(suggested_words, ensure_ascii=False)),
            )

    def fetch_session_state(self, session_id: str) -> Optional[Dict[str, Any]]:
        with self.connection() as conn:
            sess = conn.execute(
                """
                SELECT id, trigger_type, conversation_intent, scenario, hour_bucket,
                       interlocutor_context, committed
                FROM sessions WHERE id = ?
                """,
                (session_id,),
            ).fetchone()
            if not sess:
                return None
            last_log = conn.execute(
                """
                SELECT id, step_index, context_path, suggested_words
                FROM interaction_logs
                WHERE session_id = ?
                ORDER BY step_index DESC
                LIMIT 1
                """,
                (session_id,),
            ).fetchone()
            core_words = {
                r["word"] for r in conn.execute("SELECT word FROM core_vocabulary").fetchall()
            }
            return {
                "session": dict(sess),
                "last_log": dict(last_log) if last_log else None,
                "core_words": core_words,
            }

    def record_step_transition(
        self,
        session_id: str,
        prev_log_id: Optional[int],
        next_step_index: int,
        selected_word: str,
        word_source: str,
        latency_ms: int,
        context_path: List[str],
        next_suggested_words: List[str],
        updated_intent: Optional[str],
        updated_scenario: Optional[str],
    ) -> None:
        with self.connection() as conn:
            if updated_intent or updated_scenario:
                conn.execute(
                    """
                    UPDATE sessions
                    SET conversation_intent = COALESCE(?, conversation_intent),
                        scenario = COALESCE(?, scenario)
                    WHERE id = ?
                    """,
                    (updated_intent, updated_scenario, session_id),
                )
            if prev_log_id is not None:
                conn.execute(
                    "UPDATE interaction_logs SET selected_word = ?, word_source = ?, latency_ms = ? WHERE id = ?",
                    (selected_word, word_source, latency_ms, prev_log_id),
                )
            conn.execute(
                """
                INSERT INTO interaction_logs
                    (session_id, step_index, word_source, context_path, suggested_words, selected_word, latency_ms)
                VALUES (?, ?, ?, ?, ?, NULL, 0)
                """,
                (
                    session_id,
                    next_step_index,
                    word_source,
                    json.dumps(context_path, ensure_ascii=False),
                    json.dumps(next_suggested_words, ensure_ascii=False),
                ),
            )

    def commit_and_reinforce_atomic(
        self,
        session_id: str,
        final_phrase: str,
        idempotency_key: Optional[str] = None,
    ) -> Tuple[bool, int]:
        """Confirma sesión y refuerza bigramas en UNA sola transacción atómica e idempotente."""
        with self.connection() as conn:
            sess = conn.execute(
                "SELECT trigger_type, conversation_intent, scenario, hour_bucket, committed FROM sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
            if not sess:
                raise LookupError(f"Session not found: {session_id}")
            if sess["committed"] == 1:
                return True, 0

            last_log = conn.execute(
                "SELECT context_path FROM interaction_logs WHERE session_id = ? ORDER BY step_index DESC LIMIT 1",
                (session_id,),
            ).fetchone()
            context_path: List[str] = json.loads(last_log["context_path"]) if last_log else []

            conn.execute(
                "UPDATE sessions SET final_phrase = ?, committed = 1, idempotency_key = COALESCE(?, idempotency_key) WHERE id = ?",
                (final_phrase, idempotency_key, session_id),
            )

            intent_key = sess["conversation_intent"] if sess["trigger_type"] == "conversacion" and sess["conversation_intent"] else "general"
            scenario_key = sess["scenario"] or "general"
            prev = "__START__"
            updated = 0
            for word in context_path:
                conn.execute(
                    """
                    INSERT INTO bayesian_priors
                        (trigger_type, conversation_intent, scenario, hour_bucket, prev_word, candidate_word, frequency)
                    VALUES (?, ?, ?, ?, ?, ?, 1)
                    ON CONFLICT(trigger_type, conversation_intent, scenario, hour_bucket, prev_word, candidate_word)
                    DO UPDATE SET frequency = frequency + 1, updated_at = CURRENT_TIMESTAMP
                    """,
                    (sess["trigger_type"], intent_key, scenario_key, sess["hour_bucket"], prev, word),
                )
                prev = word
                updated += 1
            return True, updated

    def query_weighted_priors(
        self,
        trigger_type: str,
        intent_key: str,
        scenario: str,
        hour_bucket: int,
        prev_word: str,
    ) -> List[Tuple[str, float]]:
        with self.connection() as conn:
            rows = conn.execute(
                """
                SELECT candidate_word,
                       SUM(
                         frequency
                         * (CASE WHEN hour_bucket = ? THEN 2.0 ELSE 1.0 END)
                         * (CASE WHEN scenario = ? THEN 1.8 ELSE 1.0 END)
                       ) AS weighted_freq
                FROM bayesian_priors
                WHERE trigger_type = ?
                  AND conversation_intent IN (?, 'general')
                  AND scenario IN (?, 'general')
                  AND hour_bucket IN (?, -1)
                  AND prev_word = ?
                GROUP BY candidate_word
                ORDER BY weighted_freq DESC
                LIMIT 30
                """,
                (hour_bucket, scenario, trigger_type, intent_key, scenario, hour_bucket, prev_word),
            ).fetchall()
            return [(r["candidate_word"], float(r["weighted_freq"])) for r in rows]

    def get_cached_pictograms(self, keys: Iterable[str]) -> Dict[str, PictogramMetadata]:
        key_list = list(set(keys))
        if not key_list:
            return {}
        placeholders = ",".join("?" for _ in key_list)
        with self.connection() as conn:
            rows = conn.execute(
                f"""
                SELECT normalized_key, surface_word, fitzgerald_category, source,
                       arasaac_id, image_url, inline_svg
                FROM pictogram_cache
                WHERE normalized_key IN ({placeholders})
                """,
                key_list,
            ).fetchall()
            return {
                r["normalized_key"]: PictogramMetadata(
                    word=r["surface_word"],
                    label=r["surface_word"].replace("_", " "),
                    fitzgerald_category=r["fitzgerald_category"],
                    source=r["source"],
                    arasaac_id=r["arasaac_id"],
                    image_url=r["image_url"],
                    inline_svg=r["inline_svg"],
                )
                for r in rows
            }

    def upsert_pictogram(self, normalized_key: str, lemma: str, meta: PictogramMetadata) -> None:
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO pictogram_cache
                    (normalized_key, surface_word, lemma, arasaac_id, source, fitzgerald_category, image_url, inline_svg)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(normalized_key) DO UPDATE SET
                    arasaac_id = excluded.arasaac_id,
                    source = excluded.source,
                    image_url = excluded.image_url,
                    inline_svg = excluded.inline_svg,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    normalized_key,
                    meta.word,
                    lemma,
                    meta.arasaac_id,
                    meta.source,
                    meta.fitzgerald_category,
                    meta.image_url,
                    meta.inline_svg,
                ),
            )
