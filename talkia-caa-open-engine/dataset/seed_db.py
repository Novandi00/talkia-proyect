#!/usr/bin/env python3
"""Seeds the SQLite database using specs/schema.sql and dataset/seed_priors.json."""
import json
import os
import sqlite3

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCHEMA_PATH = os.path.join(BASE_DIR, "specs", "schema.sql")
PRIORS_PATH = os.path.join(BASE_DIR, "dataset", "seed_priors.json")
DB_PATH = os.path.join(BASE_DIR, "backend", "talkia_caa.sqlite3")


def init_and_seed_db(db_path: str = DB_PATH) -> int:
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        schema_sql = f.read()
    with open(PRIORS_PATH, "r", encoding="utf-8") as f:
        priors_data = json.load(f)

    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(schema_sql)
        inserted = 0
        triggers = priors_data.get("triggers", {})
        for trigger_type, intents in triggers.items():
            for intent_name, transitions in intents.items():
                for prev_word, candidates in transitions.items():
                    for rank, word in enumerate(candidates):
                        weight = max(1, (len(candidates) - rank) * 5)
                        conn.execute(
                            """
                            INSERT INTO bayesian_priors
                                (trigger_type, conversation_intent, scenario, hour_bucket, prev_word, candidate_word, frequency)
                            VALUES (?, ?, 'general', -1, ?, ?, ?)
                            ON CONFLICT(trigger_type, conversation_intent, scenario, hour_bucket, prev_word, candidate_word)
                            DO UPDATE SET frequency = excluded.frequency
                            """,
                            (trigger_type, intent_name, prev_word, word, weight),
                        )
                        inserted += 1
        conn.commit()
        return inserted
    finally:
        conn.close()


if __name__ == "__main__":
    total = init_and_seed_db()
    print(f"[OK] Database initialized at {DB_PATH} with {total} Bayesian prior transitions.")
