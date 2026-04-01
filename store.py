"""
store.py — SQLite + in-memory persistence layer.

Tables:
  requests   — full WorkflowState snapshot (JSON-serialised)
  audit_logs — one row per event
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from models import WorkflowState

DB_PATH = Path(__file__).parent / "workflow.db"

# In-memory cache: request_id -> WorkflowState
_state_cache: dict[str, WorkflowState] = {}
# Idempotency key -> request_id
_idem_cache: dict[str, str] = {}


# ── Schema ──────────────────────────────────────────────────────────────────

def init_db():
    with _conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS requests (
                request_id      TEXT PRIMARY KEY,
                idempotency_key TEXT UNIQUE,
                state_json      TEXT NOT NULL,
                created_at      TEXT NOT NULL,
                updated_at      TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                request_id TEXT NOT NULL,
                stage      TEXT NOT NULL,
                event      TEXT NOT NULL,
                details    TEXT NOT NULL DEFAULT '{}',
                timestamp  TEXT NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_request ON audit_logs(request_id)")


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


# ── State CRUD ───────────────────────────────────────────────────────────────

def save_state(state: WorkflowState):
    _state_cache[state.request_id] = state
    _idem_cache[state.idempotency_key] = state.request_id

    with _conn() as conn:
        conn.execute("""
            INSERT INTO requests (request_id, idempotency_key, state_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(request_id) DO UPDATE SET
                state_json = excluded.state_json,
                updated_at = excluded.updated_at
        """, (
            state.request_id,
            state.idempotency_key,
            state.model_dump_json(),
            state.created_at,
            state.updated_at,
        ))


def get_state(request_id: str) -> Optional[WorkflowState]:
    if request_id in _state_cache:
        return _state_cache[request_id]

    with _conn() as conn:
        row = conn.execute(
            "SELECT state_json FROM requests WHERE request_id = ?", (request_id,)
        ).fetchone()

    if not row:
        return None

    state = WorkflowState.model_validate_json(row["state_json"])
    _state_cache[request_id] = state
    return state


def get_request_id_by_idempotency_key(idem_key: str) -> Optional[str]:
    if idem_key in _idem_cache:
        return _idem_cache[idem_key]

    with _conn() as conn:
        row = conn.execute(
            "SELECT request_id FROM requests WHERE idempotency_key = ?", (idem_key,)
        ).fetchone()

    if not row:
        return None

    _idem_cache[idem_key] = row["request_id"]
    return row["request_id"]


# ── Audit logs ───────────────────────────────────────────────────────────────

def log_audit_event(request_id: str, stage, event: str, details: dict = {}) -> str:
    ts = datetime.utcnow().isoformat()
    with _conn() as conn:
        conn.execute(
            "INSERT INTO audit_logs (request_id, stage, event, details, timestamp) VALUES (?,?,?,?,?)",
            (request_id, str(stage), event, json.dumps(details), ts),
        )
    return ts


def get_audit_logs(request_id: str) -> list[dict]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT stage, event, details, timestamp FROM audit_logs WHERE request_id = ? ORDER BY id",
            (request_id,),
        ).fetchall()

    return [
        {
            "stage":     row["stage"],
            "event":     row["event"],
            "details":   json.loads(row["details"]),
            "timestamp": row["timestamp"],
        }
        for row in rows
    ]
