#!/usr/bin/env python3
"""backend/main.py — Servidor Multi-Hilo Defensivo con Core+Fringe, Pictogramas y Sync Offline."""
from __future__ import annotations

from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
import os
import time
from typing import Any, Dict
from urllib.parse import parse_qs, urlparse
import uuid

from backend.core_fringe_engine import CoreFringeEngine
from backend.pictogram_service import PictogramService
from backend.repository import TalkiaRepository
from backend.schemas import (
    SchemaValidationError,
    validate_commit_request,
    validate_start_request,
    validate_step_request,
)

MAX_BODY_BYTES = 16_384
ALLOWED_ORIGIN = os.environ.get("TALKIA_CORS_ORIGIN", "*")

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("talkia.api")


def parse_hour_bucket(iso_timestamp: str) -> int:
    if not iso_timestamp:
        return datetime.now().hour
    try:
        return datetime.fromisoformat(iso_timestamp.replace("Z", "+00:00")).hour
    except ValueError:
        logger.warning(json.dumps({"event": "invalid_timestamp_fallback", "raw": iso_timestamp[:40]}))
        return datetime.now().hour


class TalKIAApplication:
    """Fachada de aplicación sin SQL acoplado, thread-safe y orientada a contratos."""

    def __init__(self, db_path: str | None = None, allow_remote_arasaac: bool = False) -> None:
        self.repo = TalkiaRepository(db_path=db_path)
        self.pictos = PictogramService(self.repo, allow_remote_lookup=allow_remote_arasaac)
        self.engine = CoreFringeEngine(self.repo, self.pictos)

    def get_core_board(self) -> Dict[str, Any]:
        slots = [s.to_dict() for s in self.engine.get_immutable_core_board()]
        return {"principle": "LAMP_2x6_IMMUTABLE", "slots": slots}

    def start_session(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        req = validate_start_request(raw_data)
        hour_bucket = parse_hour_bucket(req["timestamp"])
        session_id = str(uuid.uuid4())

        payload = self.engine.generate_step_payload(
            trigger_type=req["trigger_type"],
            hour_bucket=hour_bucket,
            context_path=[],
            conversation_intent=req["conversation_intent"],
            scenario=req["scenario"],
            interlocutor_context=req["interlocutor_context"],
        )
        self.repo.create_session_with_initial_log(
            session_id=session_id,
            trigger_type=req["trigger_type"],
            conversation_intent=req["conversation_intent"] if req["trigger_type"] == "conversacion" else None,
            scenario=req["scenario"],
            hour_bucket=hour_bucket,
            interlocutor_context=req["interlocutor_context"],
            suggested_words=payload.candidate_words,
        )
        return {
            "session_id": session_id,
            "trigger_type": req["trigger_type"],
            "scenario": req["scenario"],
            "hour_bucket": hour_bucket,
            "step_index": 0,
            "context_path": [],
            "core_board": [s.to_dict() for s in self.engine.get_immutable_core_board()],
            "payload": payload.to_dict(),
        }

    def step_session(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        req = validate_step_request(raw_data)
        state = self.repo.fetch_session_state(req["session_id"])
        if not state:
            raise LookupError(f"Session not found: {req['session_id']}")

        sess = state["session"]
        last_log = state["last_log"]
        allowed_words = set(state["core_words"])
        if last_log:
            allowed_words.update(json.loads(last_log["suggested_words"]))
        if req["selected_word"] not in allowed_words:
            raise SchemaValidationError("selected_word must belong to active Core or Fringe vocabulary")

        context_path = json.loads(last_log["context_path"]) if last_log else []
        context_path.append(req["selected_word"])
        next_step = (last_log["step_index"] + 1) if last_log else 1
        active_intent = req["conversation_intent"] or sess["conversation_intent"] or "topico_libre"
        active_scenario = req["scenario"] or sess["scenario"] or "general"

        payload = self.engine.generate_step_payload(
            trigger_type=sess["trigger_type"],
            hour_bucket=sess["hour_bucket"],
            context_path=context_path,
            conversation_intent=active_intent,
            scenario=active_scenario,
            interlocutor_context=sess["interlocutor_context"],
        )

        self.repo.record_step_transition(
            session_id=req["session_id"],
            prev_log_id=last_log["id"] if last_log else None,
            next_step_index=next_step,
            selected_word=req["selected_word"],
            word_source=req["word_source"],
            latency_ms=req["latency_ms"],
            context_path=context_path,
            next_suggested_words=payload.candidate_words,
            updated_intent=req["conversation_intent"],
            updated_scenario=req["scenario"],
        )
        return {
            "session_id": req["session_id"],
            "trigger_type": sess["trigger_type"],
            "scenario": active_scenario,
            "hour_bucket": sess["hour_bucket"],
            "step_index": next_step,
            "context_path": context_path,
            "payload": payload.to_dict(),
        }

    def commit_session(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        req = validate_commit_request(raw_data)
        committed, updated = self.repo.commit_and_reinforce_atomic(
            session_id=req["session_id"],
            final_phrase=req["final_phrase"],
            idempotency_key=req["idempotency_key"],
        )
        return {
            "session_id": req["session_id"],
            "committed": committed,
            "updated_priors_count": updated,
        }


def build_handler(app: TalKIAApplication):
    class DefensiveCAAHandler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args: Any) -> None:
            return

        def _send_json(self, status: int, payload: Dict[str, Any], elapsed_ms: float = 0.0) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", ALLOWED_ORIGIN)
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("X-Process-Time-Ms", f"{elapsed_ms:.2f}")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_OPTIONS(self) -> None:
            self._send_json(200, {"status": "ok"})

        def do_GET(self) -> None:
            t0 = time.perf_counter()
            parsed = urlparse(self.path)
            if parsed.path == "/core-board":
                res = app.get_core_board()
                return self._send_json(200, res, (time.perf_counter() - t0) * 1000)
            if parsed.path == "/pictograms/resolve":
                words = parse_qs(parsed.query).get("w", [])[:20]
                items = [m.to_dict() for m in app.pictos.resolve_batch(words)]
                return self._send_json(200, {"items": items}, (time.perf_counter() - t0) * 1000)
            self._send_json(404, {"error": "Endpoint not found"})

        def do_POST(self) -> None:
            t0 = time.perf_counter()
            path = urlparse(self.path).path
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length < 0 or length > MAX_BODY_BYTES:
                    return self._send_json(413, {"error": "Payload exceeds 16KB limit"})
                raw = self.rfile.read(length).decode("utf-8") if length else "{}"
                data = json.loads(raw)
                if path == "/session/start":
                    out = app.start_session(data)
                elif path == "/session/step":
                    out = app.step_session(data)
                elif path == "/session/commit":
                    out = app.commit_session(data)
                else:
                    return self._send_json(404, {"error": f"Unknown endpoint: {path}"})
                elapsed = (time.perf_counter() - t0) * 1000
                logger.info(json.dumps({"path": path, "status": 200, "elapsed_ms": round(elapsed, 2)}))
                self._send_json(200, out, elapsed)
            except (ValueError, json.JSONDecodeError, SchemaValidationError) as exc:
                self._send_json(422, {"error": str(exc)}, (time.perf_counter() - t0) * 1000)
            except LookupError as exc:
                self._send_json(404, {"error": str(exc)}, (time.perf_counter() - t0) * 1000)
            except Exception:
                logger.exception("Unhandled server error")
                self._send_json(500, {"error": "Internal server error"}, (time.perf_counter() - t0) * 1000)

    return DefensiveCAAHandler


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    application = TalKIAApplication()
    server = ThreadingHTTPServer(("0.0.0.0", port), build_handler(application))
    print(f"TalKIA CAA-Open-Engine v2.0 listening on http://0.0.0.0:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
