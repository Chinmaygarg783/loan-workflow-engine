"""
workflow.py — Workflow state machine.

Orchestrates the full loan decision pipeline:
  RECEIVED → VALIDATED → RULES_EVALUATED → EXTERNAL_CHECK_PENDING
    → (retries) → APPROVED | REJECTED | MANUAL_REVIEW | FAILED

Every state transition is written to the audit log before any other action.
"""

from datetime import datetime

from models import WorkflowState, WorkflowStage, AuditEvent
import store
import engine
import external
import ai_agent


# ── Internal helpers ───────────────────────────────────────────────────────────
def _now() -> str:
    return datetime.utcnow().isoformat()


def _add_audit(state: WorkflowState, event: str, details: dict = {}):
    """Append an audit event to the state and persist it to SQLite."""
    ts = store.log_audit_event(state.request_id, state.current_stage, event, details)
    state.audit_trail.append(
        AuditEvent(timestamp=ts, stage=state.current_stage, event=event, details=details)
    )
    state.updated_at = _now()


def transition(state: WorkflowState, new_stage: WorkflowStage, event: str, details: dict = {}):
    """Change the workflow stage, log the transition, and persist state."""
    old = state.current_stage
    state.current_stage = new_stage
    _add_audit(state, event, {"from": old, "to": new_stage, **details})
    store.save_state(state)


# ── Main pipeline ──────────────────────────────────────────────────────────────
def process_application(state: WorkflowState, config: dict) -> WorkflowState:
    """
    Run the complete loan decision workflow.

    Stages executed (in order):
      1. Schema already validated by Pydantic — log it.
      2. Evaluate deterministic business rules from config.
      3. Call external credit bureau (with retries).
      4. AI review for ambiguous cases.
      5. Emit final decision.
    """
    data = state.data

    # ── Stage 1: VALIDATED ────────────────────────────────────────────────────
    transition(
        state,
        WorkflowStage.VALIDATED,
        "Schema validation passed",
        {"validated_fields": list(data.model_fields.keys())},
    )

    # ── Stage 2: RULES_EVALUATED ──────────────────────────────────────────────
    rules = config["rules"]
    rule_decision, triggered_rules = engine.evaluate_rules(data, rules)

    transition(
        state,
        WorkflowStage.RULES_EVALUATED,
        "Business rules evaluated",
        {"decision": rule_decision, "rules_triggered": triggered_rules},
    )

    # Hard REJECT — no further processing needed
    if rule_decision == "REJECT":
        reasons = [r["description"] for r in triggered_rules if r["action"] == "REJECT"]
        state.final_decision = "REJECTED"
        state.decision_explanation = "Automatic rejection — " + "; ".join(reasons)
        transition(
            state,
            WorkflowStage.REJECTED,
            "Application automatically rejected by rule engine",
            {"rejection_reasons": reasons},
        )
        return state

    # ── Stage 3: EXTERNAL_CHECK_PENDING (with retries) ────────────────────────
    max_retries = config["workflow"]["max_retries"]
    credit_result = None

    transition(state, WorkflowStage.EXTERNAL_CHECK_PENDING, "Initiating external credit bureau check")

    while state.retry_count <= max_retries:
        try:
            credit_result = external.check_credit(state.request_id, data.credit_score)
            _add_audit(state, "External credit check succeeded", credit_result)
            break

        except external.ExternalServiceError as exc:
            state.retry_count += 1
            if state.retry_count <= max_retries:
                transition(
                    state,
                    WorkflowStage.RETRY_SCHEDULED,
                    f"External check failed — scheduling retry {state.retry_count}/{max_retries}",
                    {"error": str(exc), "retry_number": state.retry_count},
                )
            else:
                # Retries exhausted
                _add_audit(
                    state,
                    "External check failed after all retries",
                    {"error": str(exc), "total_retries": state.retry_count - 1},
                )
                state.final_decision = "MANUAL_REVIEW"
                state.decision_explanation = (
                    f"External credit bureau unreachable after {max_retries} retries. "
                    "Human review required."
                )
                transition(
                    state,
                    WorkflowStage.MANUAL_REVIEW,
                    "Escalated to manual review: external dependency exhausted",
                    {"retries_attempted": state.retry_count - 1},
                )
                return state

    # ── Stage 4: AI Review (ambiguous cases only) ─────────────────────────────
    ambiguous, ambiguity_reason = engine.is_ambiguous(data, config)

    ai_needed = rule_decision == "AMBIGUOUS" or ambiguous

    if ai_needed:
        context_parts = []
        if rule_decision == "AMBIGUOUS":
            context_parts.append("No deterministic approval or rejection rule was triggered")
        if ambiguity_reason:
            context_parts.append(ambiguity_reason)
        full_context = "; ".join(context_parts)

        try:
            _add_audit(state, "Escalating to AI review agent", {"reason": full_context})
            ai_result = ai_agent.ai_review(data, full_context)
            state.ai_review = ai_result

            _add_audit(
                state,
                "AI review completed",
                {
                    "recommendation": ai_result.recommendation,
                    "confidence":     ai_result.confidence,
                    "explanation":    ai_result.explanation,
                    "next_step":      ai_result.next_step,
                },
            )

            # Act on AI recommendation
            if ai_result.recommendation == "APPROVE" and ai_result.confidence >= 0.75:
                state.final_decision = "APPROVED"
                state.decision_explanation = (
                    f"AI-assisted approval (confidence {ai_result.confidence:.0%}): "
                    f"{ai_result.explanation}"
                )
                transition(
                    state,
                    WorkflowStage.APPROVED,
                    "Approved by AI review agent",
                    {"confidence": ai_result.confidence},
                )

            elif ai_result.recommendation == "REJECT":
                state.final_decision = "REJECTED"
                state.decision_explanation = f"AI-assisted rejection: {ai_result.explanation}"
                transition(
                    state,
                    WorkflowStage.REJECTED,
                    "Rejected by AI review agent",
                    {"confidence": ai_result.confidence},
                )

            else:
                # Low confidence or explicit MANUAL_REVIEW
                state.final_decision = "MANUAL_REVIEW"
                state.decision_explanation = (
                    f"AI recommends human review (confidence {ai_result.confidence:.0%}): "
                    f"{ai_result.explanation}"
                )
                transition(
                    state,
                    WorkflowStage.MANUAL_REVIEW,
                    "Escalated to manual review per AI recommendation",
                    {
                        "ai_recommendation": ai_result.recommendation,
                        "confidence":        ai_result.confidence,
                    },
                )

        except Exception as exc:
            # AI unavailable — fail safe to manual review
            _add_audit(state, "AI review failed — falling back to manual review", {"error": str(exc)})
            state.final_decision = "MANUAL_REVIEW"
            state.decision_explanation = "AI review service unavailable; manual review required."
            transition(
                state,
                WorkflowStage.MANUAL_REVIEW,
                "AI review failed — sent to manual review",
                {"error": str(exc)},
            )

    else:
        # ── Stage 5: Clear automatic APPROVE ─────────────────────────────────
        approved_rules = [r["description"] for r in triggered_rules if r["action"] == "APPROVE"]
        state.final_decision = "APPROVED"
        state.decision_explanation = (
            "Automatic approval — " + "; ".join(approved_rules)
            if approved_rules
            else "Application meets all lending criteria"
        )
        transition(
            state,
            WorkflowStage.APPROVED,
            "Application automatically approved by rule engine",
            {
                "approval_rules": approved_rules,
                "credit_verified": credit_result.get("verified_credit_score") if credit_result else None,
            },
        )

    return state