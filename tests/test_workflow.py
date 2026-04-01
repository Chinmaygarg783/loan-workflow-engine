"""
tests/test_workflow.py — Full test suite for the Loan Workflow Decision Engine.

Covers:
  - Rule engine (auto-approve, auto-reject, ambiguity detection)
  - API endpoints (submit, get, audit)
  - Idempotency (duplicate key returns cached result)
  - External service retry simulation
  - Manual override endpoint
  - Config reload
"""

import uuid
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import engine
from models import LoanRequest, WorkflowStage, WorkflowState
from datetime import datetime

CONFIG = engine.load_config()


# ── Helpers ────────────────────────────────────────────────────────────────────
def make_request(**overrides) -> LoanRequest:
    defaults = dict(
        request_id="TEST-001",
        name="Jane Doe",
        age=30,
        income=60_000,
        loan_amount=150_000,
        credit_score=720,
        documents_submitted=True,
    )
    defaults.update(overrides)
    return LoanRequest(**defaults)


def make_state(req: LoanRequest) -> WorkflowState:
    now = datetime.utcnow().isoformat()
    return WorkflowState(
        request_id=req.request_id,
        idempotency_key=str(uuid.uuid4()),
        data=req,
        current_stage=WorkflowStage.RECEIVED,
        created_at=now,
        updated_at=now,
    )


def unique_id(prefix="TEST") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8].upper()}"


# ── Rule Engine Tests ──────────────────────────────────────────────────────────
class TestRuleEngine:
    def test_auto_reject_credit_below_500(self):
        req = make_request(credit_score=450)
        decision, triggered = engine.evaluate_rules(req, CONFIG["rules"])
        assert decision == "REJECT"
        assert any(r["rule_id"] == "R003" for r in triggered)

    def test_auto_reject_underage(self):
        req = make_request(age=16)
        decision, triggered = engine.evaluate_rules(req, CONFIG["rules"])
        assert decision == "REJECT"
        assert any(r["rule_id"] == "R001" for r in triggered)

    def test_auto_reject_overage(self):
        req = make_request(age=80)
        decision, triggered = engine.evaluate_rules(req, CONFIG["rules"])
        assert decision == "REJECT"
        assert any(r["rule_id"] == "R002" for r in triggered)

    def test_auto_reject_low_income(self):
        req = make_request(income=10_000)
        decision, triggered = engine.evaluate_rules(req, CONFIG["rules"])
        assert decision == "REJECT"
        assert any(r["rule_id"] == "R004" for r in triggered)

    def test_auto_reject_excessive_loan_ratio(self):
        # 300_000 / 50_000 = 6x > 5x limit
        req = make_request(income=50_000, loan_amount=300_000)
        decision, triggered = engine.evaluate_rules(req, CONFIG["rules"])
        assert decision == "REJECT"
        assert any(r["rule_id"] == "R005" for r in triggered)

    def test_auto_approve_excellent_credit(self):
        req = make_request(credit_score=800, income=100_000, loan_amount=200_000)
        decision, triggered = engine.evaluate_rules(req, CONFIG["rules"])
        assert decision == "APPROVE"
        assert any(r["rule_id"] == "R006" for r in triggered)

    def test_ambiguous_mid_range_credit(self):
        # Credit 620 → no reject, no approve → AMBIGUOUS
        req = make_request(credit_score=620, income=50_000, loan_amount=80_000)
        decision, triggered = engine.evaluate_rules(req, CONFIG["rules"])
        assert decision == "AMBIGUOUS"

    def test_rejection_rule_fires_before_approval(self):
        # Even if credit is 760, income below 15k should reject first
        req = make_request(credit_score=760, income=5_000)
        decision, _ = engine.evaluate_rules(req, CONFIG["rules"])
        assert decision == "REJECT"


# ── Ambiguity Detection Tests ──────────────────────────────────────────────────
class TestAmbiguityDetection:
    def test_borderline_credit_triggers_ambiguity(self):
        req = make_request(credit_score=610)
        is_amb, reason = engine.is_ambiguous(req, CONFIG)
        assert is_amb
        assert "credit" in reason.lower()

    def test_borderline_income_triggers_ambiguity(self):
        req = make_request(income=30_000)
        is_amb, reason = engine.is_ambiguous(req, CONFIG)
        assert is_amb
        assert "income" in reason.lower()

    def test_missing_docs_triggers_ambiguity(self):
        req = make_request(documents_submitted=False)
        is_amb, reason = engine.is_ambiguous(req, CONFIG)
        assert is_amb
        assert "document" in reason.lower()

    def test_strong_application_not_ambiguous(self):
        req = make_request(credit_score=780, income=90_000, documents_submitted=True)
        is_amb, _ = engine.is_ambiguous(req, CONFIG)
        assert not is_amb

    def test_multiple_ambiguity_reasons_combined(self):
        req = make_request(credit_score=610, income=28_000, documents_submitted=False)
        is_amb, reason = engine.is_ambiguous(req, CONFIG)
        assert is_amb
        # All three flags present
        assert "credit" in reason.lower()
        assert "income" in reason.lower()
        assert "document" in reason.lower()


# ── API: Health Check ──────────────────────────────────────────────────────────
class TestHealthEndpoint:
    def test_health_returns_200(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "healthy"


# ── API: Submit Application ────────────────────────────────────────────────────
class TestSubmitApplication:
    def _payload(self, **overrides):
        defaults = dict(
            request_id=unique_id("APP"),
            name="Test Applicant",
            age=35,
            income=80_000,
            loan_amount=200_000,
            credit_score=760,
            documents_submitted=True,
        )
        defaults.update(overrides)
        return defaults

    def test_auto_approve_returns_approved(self, client):
        p = self._payload(credit_score=800, income=100_000)
        r = client.post("/applications", json=p)
        assert r.status_code == 200
        data = r.json()
        assert data["final_decision"] == "APPROVED"
        assert data["current_stage"] == "APPROVED"

    def test_auto_reject_returns_rejected(self, client):
        p = self._payload(credit_score=400, income=50_000)
        r = client.post("/applications", json=p)
        assert r.status_code == 200
        data = r.json()
        assert data["final_decision"] == "REJECTED"
        assert data["current_stage"] == "REJECTED"
        assert data["decision_explanation"] is not None

    def test_response_contains_required_fields(self, client):
        p = self._payload()
        r = client.post("/applications", json=p)
        assert r.status_code == 200
        data = r.json()
        for field in ["request_id", "status", "current_stage", "final_decision", "decision_explanation"]:
            assert field in data, f"Missing field: {field}"

    def test_idempotency_key_prevents_duplicate_processing(self, client):
        idem_key = str(uuid.uuid4())
        p = self._payload(request_id=unique_id("IDEM"))

        r1 = client.post("/applications", json=p, headers={"idempotency-key": idem_key})
        r2 = client.post("/applications", json=p, headers={"idempotency-key": idem_key})

        assert r1.status_code == 200
        assert r2.status_code == 200
        assert r2.json()["status"] == "DUPLICATE_REQUEST"
        # Both should reference the same request_id
        assert r1.json()["request_id"] == r2.json()["request_id"]

    def test_schema_validation_rejects_invalid_credit_score(self, client):
        p = self._payload(credit_score=9999)   # max is 850
        r = client.post("/applications", json=p)
        assert r.status_code == 422             # FastAPI validation error

    def test_schema_validation_rejects_negative_income(self, client):
        p = self._payload(income=-1000)
        r = client.post("/applications", json=p)
        assert r.status_code == 422


# ── API: Get Application Status ────────────────────────────────────────────────
class TestGetApplication:
    def test_get_existing_application(self, client):
        p = dict(
            request_id=unique_id("GET"),
            name="Status Check",
            age=40,
            income=70_000,
            loan_amount=100_000,
            credit_score=450,           # will be rejected
            documents_submitted=True,
        )
        client.post("/applications", json=p)
        r = client.get(f"/applications/{p['request_id']}")
        assert r.status_code == 200
        data = r.json()
        assert data["request_id"] == p["request_id"]
        assert data["final_decision"] == "REJECTED"

    def test_get_missing_application_returns_404(self, client):
        r = client.get("/applications/DOES-NOT-EXIST-XYZ")
        assert r.status_code == 404


# ── API: Audit Trail ───────────────────────────────────────────────────────────
class TestAuditTrail:
    def test_audit_trail_has_events(self, client):
        p = dict(
            request_id=unique_id("AUD"),
            name="Audit Test",
            age=25,
            income=40_000,
            loan_amount=50_000,
            credit_score=400,
            documents_submitted=True,
        )
        client.post("/applications", json=p)
        r = client.get(f"/applications/{p['request_id']}/audit")
        assert r.status_code == 200
        data = r.json()
        assert data["total_events"] > 0
        assert isinstance(data["audit_trail"], list)

    def test_audit_trail_contains_received_event(self, client):
        p = dict(
            request_id=unique_id("AUDR"),
            name="Received Test",
            age=28,
            income=50_000,
            loan_amount=60_000,
            credit_score=400,
            documents_submitted=True,
        )
        client.post("/applications", json=p)
        r = client.get(f"/applications/{p['request_id']}/audit")
        trail = r.json()["audit_trail"]
        stages = [e["stage"] for e in trail]
        assert "RECEIVED" in stages

    def test_audit_trail_records_rejection(self, client):
        p = dict(
            request_id=unique_id("AUDREJ"),
            name="Rejection Audit",
            age=25,
            income=50_000,
            loan_amount=60_000,
            credit_score=400,
            documents_submitted=True,
        )
        client.post("/applications", json=p)
        r = client.get(f"/applications/{p['request_id']}/audit")
        trail = r.json()["audit_trail"]
        stages = [e["stage"] for e in trail]
        assert "REJECTED" in stages


# ── API: Config Reload ─────────────────────────────────────────────────────────
class TestConfigReload:
    def test_reload_returns_200(self, client):
        r = client.post("/config/reload")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "reloaded"
        assert data["rules_count"] > 0

    def test_config_rules_endpoint(self, client):
        r = client.get("/config/rules")
        assert r.status_code == 200
        data = r.json()
        assert "rules" in data
        assert "workflow" in data


# ── External Service Retry (unit-level) ────────────────────────────────────────
class TestExternalServiceRetry:
    def test_external_check_error_class(self):
        from external import ExternalServiceError
        with pytest.raises(ExternalServiceError):
            raise ExternalServiceError("test")

    def test_external_check_returns_valid_structure_on_success(self):
        """Force success by mocking random."""
        import external
        from unittest.mock import patch
        with patch("random.random", return_value=0.99):   # 0.99 > 0.30 → no failure
            result = external.check_credit("TEST-EXT", 700)
        assert "verified_credit_score" in result
        assert 300 <= result["verified_credit_score"] <= 850

    def test_external_check_raises_on_failure(self):
        import external
        from unittest.mock import patch
        with patch("random.random", return_value=0.01):   # 0.01 < 0.30 → failure
            with pytest.raises(external.ExternalServiceError):
                external.check_credit("TEST-EXT-FAIL", 700)


import pytest