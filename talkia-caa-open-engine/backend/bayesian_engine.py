"""Empirical Bayesian Prior Engine with Laplace Smoothing for TalKIA."""
from typing import List, Tuple
from backend.db import get_db_connection

FALLBACK_POOL = [
    "yo", "quiero", "sí", "no", "gracias", "por_favor",
    "ahora", "después", "más", "bien", "ayuda", "hablar",
    "cómo", "qué", "dónde", "cuándo", "mucho", "poco"
]


class BayesianEngine:
    """Computes P(W_n | Trigger, Intent, HourBucket, W_{n-1}) from SQLite priors."""

    @staticmethod
    def get_top_candidates(
        trigger_type: str,
        hour_bucket: int,
        context_path: List[str],
        conversation_intent: str = "general",
        k: int = 10,
    ) -> Tuple[List[str], float]:
        prev_word = context_path[-1] if context_path else "__START__"
        intent_key = conversation_intent if trigger_type == "conversacion" else "general"

        with get_db_connection() as conn:
            # Combine exact hour_bucket (weight 2.0) and global bucket -1 (weight 1.0)
            rows = conn.execute(
                """
                SELECT candidate_word,
                       SUM(CASE WHEN hour_bucket = ? THEN frequency * 2.0 ELSE frequency * 1.0 END) AS score
                FROM bayesian_priors
                WHERE trigger_type = ?
                  AND conversation_intent IN (?, 'general')
                  AND hour_bucket IN (?, -1)
                  AND prev_word = ?
                GROUP BY candidate_word
                ORDER BY score DESC
                LIMIT ?
                """,
                (hour_bucket, trigger_type, intent_key, hour_bucket, prev_word, k),
            ).fetchall()

            candidates = [r["candidate_word"] for r in rows]

            # Backoff to __START__ of the same trigger/intent if unseen bigram
            if len(candidates) < k:
                backoff_rows = conn.execute(
                    """
                    SELECT candidate_word, SUM(frequency) AS score
                    FROM bayesian_priors
                    WHERE trigger_type = ?
                      AND conversation_intent IN (?, 'general')
                      AND prev_word = '__START__'
                    GROUP BY candidate_word
                    ORDER BY score DESC
                    LIMIT 20
                    """,
                    (trigger_type, intent_key),
                ).fetchall()
                for r in backoff_rows:
                    w = r["candidate_word"]
                    if w not in candidates and w not in context_path:
                        candidates.append(w)
                    if len(candidates) == k:
                        break

        # Final deterministic padding to strictly guarantee 10 unique items
        for fw in FALLBACK_POOL:
            if len(candidates) >= k:
                break
            if fw not in candidates:
                candidates.append(fw)

        confidence = 0.92 if len(rows) >= 5 else 0.75
        return candidates[:k], confidence

    @staticmethod
    def construct_natural_sentence(
        trigger_type: str,
        context_path: List[str],
        conversation_intent: str = "general",
    ) -> str:
        if not context_path:
            defaults = {
                "saludo": "¡Hola! ¿Cómo estás?",
                "despedida": "¡Hasta luego! Nos vemos pronto.",
                "necesidades": "Necesito pedirte algo, por favor.",
                "emociones": "Quiero compartir cómo me siento hoy.",
                "asistencia": "¿Me podés ayudar un momento, por favor?",
                "conversacion": "Me gustaría conversar con vos.",
            }
            return defaults.get(trigger_type, "Hola.")

        clean_words = [w.replace("_", " ") for w in context_path]
        raw = " ".join(clean_words).strip()
        if not raw:
            return "Hola."

        # Format interrogative sentences properly in Spanish
        if conversation_intent == "pregunta" or raw.startswith("¿"):
            if not raw.startswith("¿"):
                raw = "¿" + raw
            if not raw.endswith("?"):
                raw = raw + "?"
            return raw[0] + raw[1].upper() + raw[2:] if len(raw) > 2 else raw

        sentence = raw[0].upper() + raw[1:]
        if not sentence.endswith((".", "!", "?")):
            sentence += "."
        return sentence

    @staticmethod
    def reinforce_path(
        trigger_type: str,
        hour_bucket: int,
        context_path: List[str],
        conversation_intent: str = "general",
    ) -> int:
        if not context_path:
            return 0
        intent_key = conversation_intent if trigger_type == "conversacion" else "general"
        updated = 0
        with get_db_connection() as conn:
            prev = "__START__"
            for word in context_path:
                conn.execute(
                    """
                    INSERT INTO bayesian_priors
                        (trigger_type, conversation_intent, hour_bucket, prev_word, candidate_word, frequency)
                    VALUES (?, ?, ?, ?, ?, 1)
                    ON CONFLICT(trigger_type, conversation_intent, hour_bucket, prev_word, candidate_word)
                    DO UPDATE SET frequency = frequency + 1, updated_at = CURRENT_TIMESTAMP
                    """,
                    (trigger_type, intent_key, hour_bucket, prev, word),
                )
                prev = word
                updated += 1
        return updated
