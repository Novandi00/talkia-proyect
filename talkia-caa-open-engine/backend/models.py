"""Contract Validator and Dataclasses enforcing specs/llm_contract.json."""
from dataclasses import dataclass, asdict
from typing import List, Dict, Any

VALID_TRIGGERS = {"saludo", "despedida", "necesidades", "emociones", "asistencia", "conversacion"}
VALID_CONVERSATION_MODES = {"estandar", "pregunta", "afirmacion", "respuesta", "topico_libre"}


@dataclass
class LLMContractPayload:
    suggested_topic: str
    conversation_mode: str
    candidate_words: List[str]
    constructed_sentence: str
    confidence_score: float

    def validate(self) -> None:
        if not isinstance(self.suggested_topic, str) or len(self.suggested_topic) > 60:
            raise ValueError("Invalid suggested_topic: must be string <= 60 chars")
        if self.conversation_mode not in VALID_CONVERSATION_MODES:
            raise ValueError(f"Invalid conversation_mode: {self.conversation_mode}")
        if not isinstance(self.candidate_words, list) or len(self.candidate_words) != 10:
            raise ValueError(f"candidate_words must contain exactly 10 items, got {len(self.candidate_words)}")
        if len(set(self.candidate_words)) != 10:
            raise ValueError("candidate_words must contain 10 unique strings")
        if not isinstance(self.constructed_sentence, str) or not self.constructed_sentence.strip():
            raise ValueError("constructed_sentence must be a non-empty string")
        if not (0.0 <= float(self.confidence_score) <= 1.0):
            raise ValueError("confidence_score must be between 0.0 and 1.0")

    def to_dict(self) -> Dict[str, Any]:
        self.validate()
        return asdict(self)
