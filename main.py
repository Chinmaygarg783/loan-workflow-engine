"""
main.py — FastAPI application entry point.

Endpoints:
  POST   /applications                        Submit a loan application
  GET    /applications/{request_id}           Get current status
  GET    /applications/{request_id}/audit     Full audit trail
  POST   /applications/{request_id}/override  Manual override for MANUAL_REVIEW cases
  GET    /config/rules                        View live rule configuration
  POST   /config/reload                       Hot-reload config without restart
  GET    /health                              Health check
"""

import uuid
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse

from models import LoanRequest, WorkflowState, WorkflowStage
import store
import engine
import workflow as wf

# ── App bootstrap ──────────────────────────────────────────────────────────────
app = FastAPI(
    title="Loan Workflow Decision Engine",
    description="Configurable workflow engine with deterministic rules + AI-assisted review",
    version="1.0.0",
)

CONFIG: dict = {}


@app.on_event("startup")
def startup():
    store.init_db()
    global CONFIG
    CONFIG = engine.load_config()
    print(f"[startup] Loaded {len(CONFIG['rules'])} rules from config.json")


# ── Endpoints ──────────────────────────────────────────────────────────────────

@app.post("/applications", summary="Submit a loan application")
def submit_application(
    request: LoanRequest,
    idempotency_key: Optional[str] = Header(None, alias="idempotency-key"),
):
    """
    Submit a loan application for processing.

    - Idempotency-Key header prevents duplicate processing.
    - Workflow runs synchronously and returns the final decision.
    """
    # Generate key if caller didn't supply one
    if not idempotency_key:
        idempotency_key = str(uuid.uuid4())

    # ── Idempotency check ──────────────────────────────────────────────────────
    existing_id = store.get_request_id_by_idempotency_key(idempotency_key)
    if existing_id:
        cached = store.get_state(existing_id)
        return {
            "status":               "DUPLICATE_REQUEST",
            "message":              "Idempotency key already used — returning cached result.",
            "idempotency_key":      idempotency_key,
            "request_id":           cached.request_id,
            "current_stage":        cached.current_stage,
            "final_decision":       cached.final_decision,
            "decision_explanation": cached.decision_explanation,
            "ai_review":            cached.ai_review.model_dump() if cached.ai_review else None,
        }

    # ── Create initial workflow state ──────────────────────────────────────────
    now = datetime.utcnow().isoformat()
    state = WorkflowState(
        request_id=request.request_id,
        idempotency_key=idempotency_key,
        data=request,
        current_stage=WorkflowStage.RECEIVED,
        created_at=now,
        updated_at=now,
    )
    store.save_state(state)
    store.log_audit_event(
        request.request_id,
        WorkflowStage.RECEIVED,
        "Application received",
        {"idempotency_key": idempotency_key, "applicant": request.name},
    )

    # ── Run workflow ───────────────────────────────────────────────────────────
    try:
        final_state = wf.process_application(state, CONFIG)
    except Exception as exc:
        state.current_stage = WorkflowStage.FAILED
        state.final_decision = "FAILED"
        state.decision_explanation = f"Unexpected workflow error: {exc}"
        store.save_state(state)
        return {
            "status":               "ERROR",
            "message":              "Workflow encountered an unexpected error.",
            "request_id":           request.request_id,
            "current_stage":        WorkflowStage.FAILED,
            "final_decision":       "FAILED",
            "decision_explanation": state.decision_explanation,
        }

    return {
        "status":               "PROCESSED",
        "message":              "Application processed successfully.",
        "idempotency_key":      idempotency_key,
        "request_id":           final_state.request_id,
        "current_stage":        final_state.current_stage,
        "final_decision":       final_state.final_decision,
        "decision_explanation": final_state.decision_explanation,
        "ai_review":            final_state.ai_review.model_dump() if final_state.ai_review else None,
        "retry_count":          final_state.retry_count,
        "created_at":           final_state.created_at,
        "updated_at":           final_state.updated_at,
    }


@app.get("/applications/{request_id}", summary="Get application status")
def get_application(request_id: str):
    state = store.get_state(request_id)
    if not state:
        raise HTTPException(status_code=404, detail=f"Application '{request_id}' not found.")

    return {
        "request_id":           state.request_id,
        "current_stage":        state.current_stage,
        "final_decision":       state.final_decision,
        "decision_explanation": state.decision_explanation,
        "retry_count":          state.retry_count,
        "ai_review":            state.ai_review.model_dump() if state.ai_review else None,
        "created_at":           state.created_at,
        "updated_at":           state.updated_at,
    }


@app.get("/applications/{request_id}/audit", summary="Full audit trail")
def get_audit_trail(request_id: str):
    """Returns every state transition and event for a given application."""
    state = store.get_state(request_id)
    if not state:
        raise HTTPException(status_code=404, detail=f"Application '{request_id}' not found.")

    logs = store.get_audit_logs(request_id)
    return {
        "request_id":     request_id,
        "current_stage":  state.current_stage,
        "final_decision": state.final_decision,
        "total_events":   len(logs),
        "audit_trail":    logs,
    }


@app.post("/applications/{request_id}/override", summary="Manual override")
def manual_override(request_id: str, decision: str, reason: str):
    """
    Manually override an application that is in MANUAL_REVIEW or FAILED stage.
    decision must be 'APPROVED' or 'REJECTED'.
    """
    state = store.get_state(request_id)
    if not state:
        raise HTTPException(status_code=404, detail=f"Application '{request_id}' not found.")

    overridable = {WorkflowStage.MANUAL_REVIEW, WorkflowStage.FAILED}
    if state.current_stage not in overridable:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot override an application in '{state.current_stage}' stage. "
                   f"Only {[s.value for s in overridable]} are overridable.",
        )

    if decision.upper() not in ("APPROVED", "REJECTED"):
        raise HTTPException(status_code=400, detail="decision must be 'APPROVED' or 'REJECTED'.")

    new_stage = WorkflowStage.APPROVED if decision.upper() == "APPROVED" else WorkflowStage.REJECTED
    state.final_decision = decision.upper()
    state.decision_explanation = f"Manual override by human operator: {reason}"

    wf.transition(
        state,
        new_stage,
        "Manual override applied",
        {"decision": decision.upper(), "reason": reason, "operator": "human"},
    )

    return {
        "status":         "OVERRIDDEN",
        "request_id":     request_id,
        "final_decision": decision.upper(),
        "message":        f"Application manually {decision.lower()}ed.",
    }


@app.get("/config/rules", summary="View live configuration")
def get_config():
    """Returns the currently loaded workflow and rules configuration."""
    return CONFIG


@app.post("/config/reload", summary="Hot-reload config without restart")
def reload_config():
    """Reload config.json at runtime — no restart required."""
    global CONFIG
    CONFIG = engine.load_config()
    return {
        "status":      "reloaded",
        "rules_count": len(CONFIG["rules"]),
        "message":     "Configuration reloaded successfully.",
    }


@app.get("/health", summary="Health check")
def health():
    return {"status": "healthy", "service": "Loan Workflow Decision Engine", "version": "1.0.0"}