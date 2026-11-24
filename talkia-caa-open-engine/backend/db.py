"""SQLite3 Connection and Repository Helpers for TalKIA (caa-open-engine)."""
import os
import sqlite3
from contextlib import contextmanager

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DB_PATH = os.environ.get(
    "TALKIA_DB_PATH", os.path.join(BASE_DIR, "backend", "talkia_caa.sqlite3")
)
SCHEMA_PATH = os.path.join(BASE_DIR, "specs", "schema.sql")


def ensure_db_initialized(db_path: str = DEFAULT_DB_PATH) -> None:
    if not os.path.exists(db_path):
        from dataset.seed_db import init_and_seed_db
        init_and_seed_db(db_path)


@contextmanager
def get_db_connection(db_path: str = DEFAULT_DB_PATH):
    ensure_db_initialized(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
