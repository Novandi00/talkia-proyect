"""backend/core_fringe_engine.py — Separación Core (LAMP) + Fringe Contextual + LLM Timeout Guard."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
import json
import os
from typing import Dict, List, Optional, Sequence, Tuple

from backend.pictogram_service import PictogramService
from backend.repository import TalkiaRepository
from backend.schemas import (
    CoreSlotContract,
    FringeStepContract,
    PictogramMetadata,
    SchemaValidationError,
)

SCENARIO_FRINGE_POOLS: Dict[str, List[str]] = {
    "casa": [
        "agua", "comer", "baño", "dormir", "frazada", "almohada",
        "tele", "música", "mamá", "papá", "luz", "silencio", "jugar", "descansar",
    ],
    "escuela": [
        "mochila", "cuaderno", "recreo", "seño", "compañero", "baño",
        "auriculares", "descanso", "dibujar", "leer", "terminé", "esperar", "pizarrón", "lápiz",
    ],
    "calle": [
        "casa", "auto", "plaza", "ruido", "auriculares", "caminar",
        "sentarme", "agua", "volver", "despacio", "semáforo", "kiosco", "frío", "calor",
    ],
    "salud": [
        "duele", "cabeza", "panza", "mi_medicación", "doctor", "descansar",
        "agua", "frío", "calor", "esperar", "tranquilo", "miedo", "camilla", "mamá",
    ],
    "general": [
        "agua", "comer", "descansar", "baño", "gracias", "por_favor",
        "después", "bien", "hablar", "cómo", "qué", "dónde", "cuándo", "mucho", "poco", "tranquilo",
    ],
}

TOPIC_LABELS: Dict[str, str] = {
    "saludo": "Saludo e inicio de contacto",
    "despedida": "Cierre de conversación",
    "necesidades": "Necesidades fisiológicas y confort",
    "emociones": "Estado emocional y autorregulación",
    "asistencia": "Solicitud de apoyo directo",
    "conversacion:pregunta": "Conversación abierta — Formular pregunta",
    "conversacion:afirmacion": "Conversación abierta — Expresar idea",
    "conversacion:respuesta": "Conversación abierta — Responder",
    "conversacion:topico_libre": "Conversación abierta — Tema contextual",
}

_LLM_POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix="talkia-fringe-llm")


class CoreFringeEngine:
    """Garantiza inmutabilidad espacial LAMP en Core y 10 sugerencias Fringe contextuales únicas."""

    def __init__(self, repo: TalkiaRepository, picto_service: PictogramService) -> None:
        self.repo = repo
        self.picto_service = picto_service

    def get_immutable_core_board(self) -> List[CoreSlotContract]:
        rows = self.repo.get_core_vocabulary()
        pictos = self.picto_service.resolve_batch([r["word"] for r in rows])
        by_word = {p.word: p for p in pictos}
        return [
            CoreSlotContract(
                slot_id=r["slot_id"],
                row_idx=r["row_idx"],
                col_idx=r["col_idx"],
                word=r["word"],
                label=r["label"],
                fitzgerald_category=r["fitzgerald_category"],
                pictogram=by_word[r["word"]],
            )
            for r in rows
        ]

    def compute_bayesian_fringe(
        self,
        trigger_type: str,
        hour_bucket: int,
        context_path: Sequence[str],
        conversation_intent: str = "general",
        scenario: str = "general",
        k: int = 10,
        alpha: float = 1.0,
    ) -> Tuple[List[str], float]:
        """Calcula P(W_n | C) con suavizado de Laplace real, excluyendo Core y evitando bucles."""
        prev_word = context_path[-1] if context_path else "__START__"
        intent_key = conversation_intent if trigger_type == "conversacion" else "general"
        core_words = {r["word"].lower() for r in self.repo.get_core_vocabulary()}
        recent_ban = {prev_word.lower()}

        raw_rows = self.repo.query_weighted_priors(
            trigger_type=trigger_type,
            intent_key=intent_key,
            scenario=scenario,
            hour_bucket=hour_bucket,
            prev_word=prev_word,
        )
        if len(raw_rows) < k and prev_word != "__START__":
            backoff_rows = self.repo.query_weighted_priors(
                trigger_type=trigger_type,
                intent_key=intent_key,
                scenario=scenario,
                hour_bucket=hour_bucket,
                prev_word="__START__",
            )
            seen_keys = {w for w, _ in raw_rows}
            raw_rows.extend((w, f * 0.5) for w, f in backoff_rows if w not in seen_keys)

        filtered: List[Tuple[str, float]] = [
            (w, freq)
            for w, freq in raw_rows
            if w.lower() not in core_words and w.lower() not in recent_ban
        ]

        vocab_size = max(len(filtered) + len(SCENARIO_FRINGE_POOLS["general"]), 24)
        total_weight = sum(freq for _, freq in filtered)
        denom = total_weight + alpha * vocab_size

        candidates: List[str] = []
        prob_mass = 0.0
        for word, freq in filtered:
            if word not in candidates:
                candidates.append(word)
                prob_mass += (freq + alpha) / denom
            if len(candidates) == k:
                break

        scenario_pool = SCENARIO_FRINGE_POOLS.get(scenario, []) + SCENARIO_FRINGE_POOLS["general"]
        for fallback_word in scenario_pool:
            if len(candidates) >= k:
                break
            if (
                fallback_word not in candidates
                and fallback_word.lower() not in core_words
                and fallback_word.lower() not in recent_ban
            ):
                candidates.append(fallback_word)

        confidence = min(0.98, max(0.52, prob_mass * 1.35)) if filtered else 0.52
        return candidates[:k], round(confidence, 3)

    @staticmethod
    def construct_sentence(
        trigger_type: str,
        context_path: Sequence[str],
        conversation_mode: str = "estandar",
    ) -> str:
        if not context_path:
            defaults = {
                "saludo": "¡Hola! ¿Cómo estás?",
                "despedida": "¡Hasta luego! Nos vemos pronto.",
                "necesidades": "Necesito pedirte algo, por favor.",
                "emociones": "Quiero expresar cómo me siento.",
                "asistencia": "¿Me podés ayudar un momento, por favor?",
                "conversacion": "Me gustaría conversar con vos.",
            }
            return defaults.get(trigger_type, "Hola.")

        tokens = [w.replace("_", " ").strip() for w in context_path if w.strip()]
        raw = " ".join(tokens)[:236].strip()
        if not raw:
            return "Hola."

        if conversation_mode == "pregunta" or raw.startswith("¿"):
            body = raw.lstrip("¿").rstrip("?.!")
            body_cap = body[0].upper() + body[1:] if len(body) > 1 else body.upper()
            return f"¿{body_cap}?"

        cap = raw[0].upper() + raw[1:]
        if not cap.endswith((".", "!", "?")):
            cap += "."
        return cap

    def generate_step_payload(
        self,
        trigger_type: str,
        hour_bucket: int,
        context_path: List[str],
        conversation_intent: str = "topico_libre",
        scenario: str = "general",
        interlocutor_context: Optional[str] = None,
        llm_budget_ms: int = 600,
    ) -> FringeStepContract:
        mode = (
            conversation_intent
            if trigger_type == "conversacion" and conversation_intent in {"pregunta", "afirmacion", "respuesta", "topico_libre"}
            else "estandar"
        )
        prior_words, prior_conf = self.compute_bayesian_fringe(
            trigger_type=trigger_type,
            hour_bucket=hour_bucket,
            context_path=context_path,
            conversation_intent=mode if mode != "estandar" else "general",
            scenario=scenario,
            k=10,
        )

        final_words, final_sentence, final_conf = self._try_constrained_llm_fringe(
            trigger_type=trigger_type,
            mode=mode,
            scenario=scenario,
            context_path=context_path,
            interlocutor_context=interlocutor_context,
            prior_anchor=prior_words,
            prior_conf=prior_conf,
            budget_ms=llm_budget_ms,
        )

        pictos: List[PictogramMetadata] = self.picto_service.resolve_batch(final_words)
        topic_key = f"conversacion:{mode}" if trigger_type == "conversacion" else trigger_type
        topic = f"{TOPIC_LABELS.get(topic_key, 'Comunicación asistida')} [{scenario}]"[:60]

        return FringeStepContract(
            suggested_topic=topic,
            conversation_mode=mode,
            candidate_words=final_words,
            constructed_sentence=final_sentence,
            confidence_score=final_conf,
            fringe_items=pictos,
        )

    def _try_constrained_llm_fringe(
        self,
        trigger_type: str,
        mode: str,
        scenario: str,
        context_path: List[str],
        interlocutor_context: Optional[str],
        prior_anchor: List[str],
        prior_conf: float,
        budget_ms: int,
    ) -> Tuple[List[str], str, float]:
        default_sentence = self.construct_sentence(trigger_type, context_path, mode)
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key or trigger_type != "conversacion":
            return prior_anchor, default_sentence, prior_conf

        def _call_gemini() -> Tuple[List[str], str, float]:
            from google import genai  # type: ignore

            core_words = {r["word"].lower() for r in self.repo.get_core_vocabulary()}
            client = genai.Client(api_key=api_key)
            prompt = (
                "Sos un motor CAA en español rioplatense (es-AR). "
                f"Escenario={scenario}, Modo={mode}, Interlocutor={interlocutor_context or 'N/A'}, "
                f"Palabras elegidas={context_path}, Ancla Bayesiana={prior_anchor}. "
                f"Prohibido incluir estas palabras Core fijas: {sorted(core_words)}. "
                "Devolvé JSON estricto con 10 candidate_words únicas (1..32 chars) y constructed_sentence."
            )
            resp = client.models.generate_content(
                model=os.environ.get("TALKIA_LLM_MODEL", "gemini-2.5-flash"),
                contents=prompt,
                config={"response_mime_type": "application/json"},
            )
            parsed = json.loads(resp.text or "{}")
            words = [w for w in parsed.get("candidate_words", []) if w.lower() not in core_words]
            if len(words) != 10 or len(set(words)) != 10:
                raise SchemaValidationError("LLM violated 10 unique non-core Fringe words invariant")
            sentence = str(parsed.get("constructed_sentence") or default_sentence)[:240]
            hybrid_conf = round(0.6 * prior_conf + 0.4 * float(parsed.get("confidence_score", 0.85)), 3)
            return words, sentence, hybrid_conf

        future = _LLM_POOL.submit(_call_gemini)
        try:
            return future.result(timeout=budget_ms / 1000.0)
        except (FuturesTimeout, Exception):
            return prior_anchor, default_sentence, prior_conf
