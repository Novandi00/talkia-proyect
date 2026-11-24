// frontend/contracts.js — Guardas de Contrato Fail-Fast
export function assertValidStepPayload(payload) {
  if (!payload || typeof payload !== "object") throw new Error("Invalid step payload object");
  const { candidate_words: words, constructed_sentence: sent, confidence_score: score } = payload;
  if (!Array.isArray(words) || words.length !== 10 || new Set(words).size !== 10) {
    throw new Error("Contract violation: candidate_words must have 10 unique items");
  }
  if (typeof sent !== "string" || sent.length === 0 || sent.length > 240) {
    throw new Error("Contract violation: constructed_sentence out of bounds");
  }
  if (typeof score !== "number" || score < 0 || score > 1) {
    throw new Error("Contract violation: confidence_score out of bounds");
  }
  return payload;
}
