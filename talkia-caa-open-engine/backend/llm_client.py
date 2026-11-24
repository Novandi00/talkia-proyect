"""Hybrid Bayesian + Constrained LLM Inference Client for TalKIA."""
from typing import List
from backend.bayesian_engine import BayesianEngine
from backend.models import LLMContractPayload

TOPIC_LABELS = {
    "saludo": "Saludo e inicio de contacto",
    "despedida": "Cierre de conversación y saludo final",
    "necesidades": "Necesidades fisiológicas y confort",
    "emociones": "Expresión de estado emocional",
    "asistencia": "Solicitud de asistencia directa",
    "conversacion:pregunta": "Conversación abierta — Formular pregunta",
    "conversacion:afirmacion": "Conversación abierta — Expresar afirmación/opinión",
    "conversacion:respuesta": "Conversación abierta — Responder al interlocutor",
    "conversacion:topico_libre": "Conversación abierta — Proponer tema dinámico",
}


class HybridInferenceClient:
    """Combines empirical SQLite priors with optional LLM re-ranking, guaranteeing contract compliance."""

    @staticmethod
    def generate_step_payload(
        trigger_type: str,
        hour_bucket: int,
        context_path: List[str],
        conversation_intent: str = "topico_libre",
    ) -> LLMContractPayload:
        mode = (
            conversation_intent
            if trigger_type == "conversacion" and conversation_intent in {"pregunta", "afirmacion", "respuesta", "topico_libre"}
            else "estandar"
        )
        candidates, confidence = BayesianEngine.get_top_candidates(
            trigger_type=trigger_type,
            hour_bucket=hour_bucket,
            context_path=context_path,
            conversation_intent=mode if mode != "estandar" else "general",
            k=10,
        )
        sentence = BayesianEngine.construct_natural_sentence(
            trigger_type=trigger_type,
            context_path=context_path,
            conversation_intent=mode,
        )
        topic_key = f"conversacion:{mode}" if trigger_type == "conversacion" else trigger_type
        topic = TOPIC_LABELS.get(topic_key, "Comunicación asistida activa")[:60]

        payload = LLMContractPayload(
            suggested_topic=topic,
            conversation_mode=mode,
            candidate_words=candidates,
            constructed_sentence=sentence,
            confidence_score=round(confidence, 3),
        )
        payload.validate()
        return payload
