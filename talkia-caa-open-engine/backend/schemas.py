"""backend/schemas.py — Validación Fail-Fast de Contratos CAA (Pydantic v2 + Stdlib Guard)."""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional
import uuid

VALID_TRIGGERS = frozenset({"saludo", "despedida", "necesidades", "emociones", "asistencia", "conversacion"})
VALID_INTENTS = frozenset({"pregunta", "afirmacion", "respuesta", "topico_libre"})
VALID_MODES = frozenset({"estandar", "pregunta", "afirmacion", "respuesta", "topico_libre"})
VALID_SCENARIOS = frozenset({"general", "casa", "escuela", "calle", "salud"})
VALID_FITZGERALD = frozenset({"pronoun", "verb", "noun", "adjective", "social", "question", "negation", "misc"})

TriggerLiteral = Literal["saludo", "despedida", "necesidades", "emociones", "asistencia", "conversacion"]
IntentLiteral = Literal["pregunta", "afirmacion", "respuesta", "topico_libre"]
ModeLiteral = Literal["estandar", "pregunta", "afirmacion", "respuesta", "topico_libre"]
ScenarioLiteral = Literal["general", "casa", "escuela", "calle", "salud"]
FitzgeraldLiteral = Literal["pronoun", "verb", "noun", "adjective", "social", "question", "negation", "misc"]


class SchemaValidationError(ValueError):
    """Excepción de contrato inválido lista para mapear a HTTP 422."""


def _validate_word_token(word: str) -> str:
    if not isinstance(word, str):
        raise SchemaValidationError("Word token must be a string")
    cleaned = word.strip()
    if not (1 <= len(cleaned) <= 32):
        raise SchemaValidationError(f"Word '{word}' violates length bounds [1..32]")
    if any(ch in cleaned for ch in ("<", ">", "\x00", "\n", "\r")):
        raise SchemaValidationError("Word contains forbidden control or HTML characters")
    return cleaned


class PictogramMetadata:
    """Representación serializable y validada de un símbolo visual CAA."""

    __slots__ = ("word", "label", "fitzgerald_category", "source", "arasaac_id", "image_url", "inline_svg")

    def __init__(
        self,
        word: str,
        label: str,
        fitzgerald_category: str = "misc",
        source: str = "local_svg",
        arasaac_id: Optional[int] = None,
        image_url: Optional[str] = None,
        inline_svg: Optional[str] = None,
    ) -> None:
        self.word = _validate_word_token(word)
        self.label = label.strip()[:32] or self.word.replace("_", " ")
        if fitzgerald_category not in VALID_FITZGERALD:
            raise SchemaValidationError(f"Invalid fitzgerald_category: {fitzgerald_category}")
        self.fitzgerald_category = fitzgerald_category
        if source not in {"arasaac", "mulberry", "local_svg"}:
            raise SchemaValidationError(f"Invalid pictogram source: {source}")
        self.source = source
        self.arasaac_id = arasaac_id
        self.image_url = image_url
        self.inline_svg = inline_svg

    def to_dict(self) -> Dict[str, Any]:
        return {
            "word": self.word,
            "label": self.label,
            "fitzgerald_category": self.fitzgerald_category,
            "source": self.source,
            "arasaac_id": self.arasaac_id,
            "image_url": self.image_url,
            "inline_svg": self.inline_svg,
        }


class CoreSlotContract:
    """Slot inmutable bajo principio LAMP (coordenadas fijas nunca cambian entre pasos)."""

    __slots__ = ("slot_id", "row_idx", "col_idx", "word", "label", "fitzgerald_category", "pictogram")

    def __init__(
        self,
        slot_id: int,
        row_idx: int,
        col_idx: int,
        word: str,
        label: str,
        fitzgerald_category: str,
        pictogram: PictogramMetadata,
    ) -> None:
        if not (0 <= slot_id < 12 and 0 <= row_idx < 2 and 0 <= col_idx < 6):
            raise SchemaValidationError("Core slot coordinates out of 2x6 LAMP bounds")
        self.slot_id = slot_id
        self.row_idx = row_idx
        self.col_idx = col_idx
        self.word = _validate_word_token(word)
        self.label = label
        self.fitzgerald_category = fitzgerald_category
        self.pictogram = pictogram

    def to_dict(self) -> Dict[str, Any]:
        return {
            "slot_id": self.slot_id,
            "row_idx": self.row_idx,
            "col_idx": self.col_idx,
            "word": self.word,
            "label": self.label,
            "fitzgerald_category": self.fitzgerald_category,
            "pictogram": self.pictogram.to_dict(),
        }


class FringeStepContract:
    """Validador estricto fail-fast alineado con specs/llm_contract.json."""

    def __init__(
        self,
        suggested_topic: str,
        conversation_mode: str,
        candidate_words: List[str],
        constructed_sentence: str,
        confidence_score: float,
        fringe_items: Optional[List[PictogramMetadata]] = None,
    ) -> None:
        if not isinstance(suggested_topic, str) or not (1 <= len(suggested_topic.strip()) <= 60):
            raise SchemaValidationError("suggested_topic must be non-empty string <= 60 chars")
        if conversation_mode not in VALID_MODES:
            raise SchemaValidationError(f"Unsupported conversation_mode: {conversation_mode}")
        if not isinstance(candidate_words, list) or len(candidate_words) != 10:
            raise SchemaValidationError("candidate_words must contain strictly 10 items")
        cleaned_words = [_validate_word_token(w) for w in candidate_words]
        if len(set(cleaned_words)) != 10:
            raise SchemaValidationError("candidate_words must contain 10 unique strings")
        if not isinstance(constructed_sentence, str) or not (1 <= len(constructed_sentence.strip()) <= 240):
            raise SchemaValidationError("constructed_sentence must be non-empty string <= 240 chars")
        score = float(confidence_score)
        if not (0.0 <= score <= 1.0):
            raise SchemaValidationError("confidence_score must be within [0.0, 1.0]")

        self.suggested_topic = suggested_topic.strip()
        self.conversation_mode = conversation_mode
        self.candidate_words = cleaned_words
        self.constructed_sentence = constructed_sentence.strip()
        self.confidence_score = round(score, 3)
        self.fringe_items = fringe_items or []

    def to_dict(self) -> Dict[str, Any]:
        base: Dict[str, Any] = {
            "suggested_topic": self.suggested_topic,
            "conversation_mode": self.conversation_mode,
            "candidate_words": self.candidate_words,
            "constructed_sentence": self.constructed_sentence,
            "confidence_score": self.confidence_score,
        }
        if self.fringe_items:
            base["fringe_items"] = [item.to_dict() for item in self.fringe_items]
        return base


def validate_start_request(data: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(data, dict):
        raise SchemaValidationError("Payload must be a JSON object")
    allowed = {"trigger_type", "conversation_intent", "scenario", "interlocutor_context", "timestamp"}
    unknown = set(data.keys()) - allowed
    if unknown:
        raise SchemaValidationError(f"Unknown fields in StartSessionRequest: {sorted(unknown)}")

    trigger = data.get("trigger_type", "saludo")
    if trigger not in VALID_TRIGGERS:
        raise SchemaValidationError(f"Invalid trigger_type: {trigger}")
    intent = data.get("conversation_intent", "topico_libre")
    if intent not in VALID_INTENTS:
        raise SchemaValidationError(f"Invalid conversation_intent: {intent}")
    scenario = data.get("scenario", "general")
    if scenario not in VALID_SCENARIOS:
        raise SchemaValidationError(f"Invalid scenario: {scenario}")
    ctx = data.get("interlocutor_context")
    if ctx is not None:
        if not isinstance(ctx, str) or len(ctx) > 200:
            raise SchemaValidationError("interlocutor_context must be string <= 200 chars")
        ctx = ctx.strip()
    return {
        "trigger_type": trigger,
        "conversation_intent": intent,
        "scenario": scenario,
        "interlocutor_context": ctx,
        "timestamp": str(data.get("timestamp", "")),
    }


def validate_step_request(data: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(data, dict):
        raise SchemaValidationError("Payload must be a JSON object")
    try:
        session_id = str(uuid.UUID(str(data["session_id"])))
    except (KeyError, ValueError) as exc:
        raise SchemaValidationError("Valid UUID session_id is required") from exc

    if "selected_word" not in data:
        raise SchemaValidationError("selected_word is required")
    selected_word = _validate_word_token(data["selected_word"])
    word_source = data.get("word_source", "fringe")
    if word_source not in {"core", "fringe"}:
        raise SchemaValidationError("word_source must be 'core' or 'fringe'")

    latency_ms = data.get("latency_ms", 0)
    if not isinstance(latency_ms, int) or latency_ms < 0 or latency_ms > 600_000:
        raise SchemaValidationError("latency_ms must be integer in [0, 600000]")

    intent = data.get("conversation_intent")
    if intent is not None and intent not in VALID_INTENTS:
        raise SchemaValidationError(f"Invalid conversation_intent: {intent}")

    scenario = data.get("scenario")
    if scenario is not None and scenario not in VALID_SCENARIOS:
        raise SchemaValidationError(f"Invalid scenario: {scenario}")

    return {
        "session_id": session_id,
        "selected_word": selected_word,
        "word_source": word_source,
        "latency_ms": latency_ms,
        "conversation_intent": intent,
        "scenario": scenario,
    }


def validate_commit_request(data: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(data, dict):
        raise SchemaValidationError("Payload must be a JSON object")
    try:
        session_id = str(uuid.UUID(str(data["session_id"])))
    except (KeyError, ValueError) as exc:
        raise SchemaValidationError("Valid UUID session_id is required") from exc
    phrase = data.get("final_phrase", "")
    if not isinstance(phrase, str) or not (1 <= len(phrase.strip()) <= 240):
        raise SchemaValidationError("final_phrase must be string in [1..240] chars")
    idem_key = data.get("idempotency_key")
    if idem_key is not None and (not isinstance(idem_key, str) or len(idem_key) > 64):
        raise SchemaValidationError("idempotency_key must be string <= 64 chars")
    return {
        "session_id": session_id,
        "final_phrase": phrase.strip(),
        "idempotency_key": idem_key,
    }
