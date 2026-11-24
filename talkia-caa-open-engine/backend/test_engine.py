#!/usr/bin/env python3
"""backend/test_engine.py — Suite Aislada para Contratos SDD, Principio LAMP, Idempotencia y Latencia < 50ms."""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import tempfile
import threading
import time
import urllib.request

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from backend.main import TalKIAApplication, build_handler
from backend.schemas import SchemaValidationError, VALID_SCENARIOS, VALID_TRIGGERS
from dataset.seed_db import init_and_seed_db
from http.server import ThreadingHTTPServer


def verify_specs_and_lamp_invariants(app: TalKIAApplication) -> None:
    baseline_core = app.get_core_board()["slots"]
    assert len(baseline_core) == 12, "Core LAMP board must contain 12 fixed slots"
    baseline_coords = [(s["slot_id"], s["row_idx"], s["col_idx"], s["word"]) for s in baseline_core]

    for trigger in VALID_TRIGGERS:
        for scenario in VALID_SCENARIOS:
            started = app.start_session({
                "trigger_type": trigger,
                "conversation_intent": "pregunta" if trigger == "conversacion" else "topico_libre",
                "scenario": scenario,
                "timestamp": "2026-11-23T09:30:00-03:00",
            })
            step_coords = [(s["slot_id"], s["row_idx"], s["col_idx"], s["word"]) for s in started["core_board"]]
            assert step_coords == baseline_coords, "LAMP Violation: Core slot moved position!"

            fringe_words = started["payload"]["candidate_words"]
            core_words = {s["word"] for s in baseline_core}
            assert len(fringe_words) == 10 and len(set(fringe_words)) == 10
            assert not (set(fringe_words) & core_words), "Fringe duplicated a fixed Core word!"


def verify_bayesian_idempotency_and_latency(app: TalKIAApplication) -> None:
    latencies_ms = []
    started = app.start_session({
        "trigger_type": "conversacion",
        "conversation_intent": "afirmacion",
        "scenario": "escuela",
        "timestamp": "2026-11-23T10:15:00-03:00",
    })
    sid = started["session_id"]

    step1 = app.step_session({
        "session_id": sid,
        "selected_word": "yo",
        "word_source": "core",
        "latency_ms": 310,
    })
    fringe_pick = step1["payload"]["candidate_words"][0]

    for _ in range(30):
        t0 = time.perf_counter()
        app.engine.generate_step_payload(
            trigger_type="conversacion",
            hour_bucket=10,
            context_path=["yo", fringe_pick],
            conversation_intent="afirmacion",
            scenario="escuela",
        )
        latencies_ms.append((time.perf_counter() - t0) * 1000.0)

    p95 = statistics.quantiles(latencies_ms, n=20)[18]
    assert p95 < 50.0, f"Offline/Cached Fringe + Pictogram P95 latency exceeded 50ms: {p95:.2f}ms"

    first_commit = app.commit_session({"session_id": sid, "final_phrase": "Yo quiero dibujar."})
    second_commit = app.commit_session({"session_id": sid, "final_phrase": "Yo quiero dibujar."})
    assert first_commit["updated_priors_count"] >= 1
    assert second_commit["updated_priors_count"] == 0, "Commit must be strictly idempotent"

    try:
        app.step_session({"session_id": sid, "selected_word": "palabra_inyectada_xyz", "latency_ms": 10})
        raise AssertionError("Expected SchemaValidationError for injected word")
    except SchemaValidationError:
        pass


def verify_http_defensive_api(app: TalKIAApplication) -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), build_handler(app))
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        # Use direct proxy-free handler for local test socket
        proxy_handler = urllib.request.ProxyHandler({})
        opener = urllib.request.build_opener(proxy_handler)
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/session/start",
            data=json.dumps({"trigger_type": "necesidades", "scenario": "casa", "timestamp": "2026-11-23T20:00:00Z"}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with opener.open(req, timeout=2.0) as resp:
            assert resp.status == 200
            assert "X-Process-Time-Ms" in resp.headers
            body = json.loads(resp.read().decode("utf-8"))
            assert len(body["payload"]["fringe_items"]) == 10
    finally:
        server.shutdown()


def main() -> None:
    parser = argparse.ArgumentParser(description="TalKIA v2.0 Spec & Accessibility Verification Suite")
    parser.add_argument("--verify-specs", action="store_true")
    parser.add_argument("--verify-bayesian", action="store_true")
    parser.add_argument("--verify-api", action="store_true")
    args = parser.parse_args()
    run_all = not (args.verify_specs or args.verify_bayesian or args.verify_api)

    with tempfile.TemporaryDirectory() as tmpdir:
        test_db = os.path.join(tmpdir, "isolated_talkia.sqlite3")
        os.environ["TALKIA_DB_PATH"] = test_db
        app = TalKIAApplication(db_path=test_db, allow_remote_arasaac=False)
        init_and_seed_db(test_db)

        if run_all or args.verify_specs:
            verify_specs_and_lamp_invariants(app)
        if run_all or args.verify_bayesian:
            verify_bayesian_idempotency_and_latency(app)
        if run_all or args.verify_api:
            verify_http_defensive_api(app)

    print("[PASS] TalKIA v2.0 Core+Fringe (LAMP), ARASAAC Cache (<50ms), Idempotency & Defensive API verified.")


if __name__ == "__main__":
    main()
