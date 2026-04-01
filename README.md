# 🏦 Loan Workflow Decision Engine

A **configurable workflow decision engine** with AI-assisted review for ambiguous loan applications.
Built in Python using FastAPI, Pydantic, SQLite, and OpenRouter GPT-4o mini.

---

## Architecture Overview

```
POST /applications
      │
      ▼
┌─────────────────────────────────────────────────────────────┐
│                      FastAPI (main.py)                       │
│  • Schema validation (Pydantic)                              │
│  • Idempotency check (SQLite + in-memory cache)              │
│  • Delegates to workflow.py                                  │
└────────────────────────────┬────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────┐
│               Workflow State Machine (workflow.py)           │
│                                                              │
│  RECEIVED → VALIDATED → RULES_EVALUATED                      │
│      │                        │                              │
│      │              ┌─────────┴─────────┐                   │
│      │           REJECT              APPROVE / AMBIGUOUS     │
│      │              │                    │                   │
│      │         [REJECTED]     EXTERNAL_CHECK_PENDING         │
│      │                            │    │                     │
│      │                        success  failure               │
│      │                            │    │                     │
│      │                            │  RETRY_SCHEDULED (×2)   │
│      │                            │    │exhausted            │
│      │                            │  MANUAL_REVIEW           │
│      │                            │                          │
│      │              ┌─────────────┘                          │
│      │         ambiguous?                                     │
│      │           yes │         no                            │
│      │           AI Review    [APPROVED]                      │
│      │               │                                        │
│      │    APPROVE/REJECT/MANUAL_REVIEW                        │
└──────┴────────────────────────────────────────────────────  ┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────┐
│                    SQLite (workflow.db)                       │
│  • requests table   — full state snapshot                    │
│  • audit_logs table — every event, timestamped               │
└─────────────────────────────────────────────────────────────┘
```

---

## Workflow Stages

| Stage | Description |
|---|---|
| `RECEIVED` | Application accepted, idempotency key registered |
| `VALIDATED` | Pydantic schema validation passed |
| `RULES_EVALUATED` | Deterministic rules from config.json applied |
| `EXTERNAL_CHECK_PENDING` | Calling external credit bureau |
| `RETRY_SCHEDULED` | External call failed — queued for retry |
| `APPROVED` | Final decision: approved |
| `REJECTED` | Final decision: rejected |
| `MANUAL_REVIEW` | Escalated to human operator |
| `FAILED` | Unexpected error |

---

## Setup

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Set your Anthropic API key (for AI review of ambiguous cases)
# Add your OpenRouter key directly in ai_agent.py
# Open ai_agent.py and set:
# api_key = "sk-or-your-key-here"

# 3. Start the server
uvicorn main:app --reload

# 4. Open docs
open http://localhost:8000/docs
```

---

## API Endpoints

### `POST /applications`
Submit a loan application for processing.

**Headers:**
- `Idempotency-Key: <string>` — optional; prevents duplicate processing

**Request body:**
```json
{
  "request_id": "LOAN-2024-001",
  "name": "Alice Smith",
  "age": 34,
  "income": 85000,
  "loan_amount": 200000,
  "credit_score": 740,
  "documents_submitted": true
}
```

**Response:**
```json
{
  "status": "PROCESSED",
  "request_id": "LOAN-2024-001",
  "current_stage": "APPROVED",
  "final_decision": "APPROVED",
  "decision_explanation": "Automatic approval — Credit score above 750...",
  "ai_review": null,
  "retry_count": 0
}
```

### `GET /applications/{request_id}`
Get current status and decision for an application.

### `GET /applications/{request_id}/audit`
Full timestamped audit trail — every state transition and event.

### `POST /applications/{request_id}/override?decision=APPROVED&reason=...`
Manually approve or reject an application stuck in `MANUAL_REVIEW`.

### `GET /config/rules`
View the currently loaded rules configuration.

### `POST /config/reload`
Hot-reload `config.json` without restarting the server.

### `GET /health`
Health check.

---

## Sample Request Scenarios

### Auto-Reject (credit score < 500)
```bash
curl -X POST http://localhost:8000/applications \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: unique-key-001" \
  -d '{"request_id":"REJ-001","name":"Bad Credit Bob","age":30,"income":50000,"loan_amount":100000,"credit_score":400,"documents_submitted":true}'
```

### Auto-Approve (credit score ≥ 750)
```bash
curl -X POST http://localhost:8000/applications \
  -H "Content-Type: application/json" \
  -d '{"request_id":"APP-001","name":"Alice Excellent","age":40,"income":120000,"loan_amount":250000,"credit_score":800,"documents_submitted":true}'
```

### AI-Assisted Review (borderline credit, missing docs)
```bash
curl -X POST http://localhost:8000/applications \
  -H "Content-Type: application/json" \
  -d '{"request_id":"AMB-001","name":"Borderline Bob","age":29,"income":45000,"loan_amount":80000,"credit_score":615,"documents_submitted":false}'
```

---

## Configuration (config.json)

Rules are evaluated **without code changes**. Add/remove/modify rules freely:

```json
{
  "workflow": {
    "max_retries": 2,
    "ambiguous_thresholds": {
      "credit_score_min": 580,
      "credit_score_max": 650
    }
  },
  "rules": [
    {
      "id": "R003",
      "name": "hard_reject_credit_score",
      "field": "credit_score",
      "operator": "lt",
      "value": 500,
      "action": "REJECT",
      "priority": 3
    }
  ]
}
```

Reload at runtime: `POST /config/reload`

---

## Run Tests

```bash
cd loan_workflow
pytest tests/ -v
```

---

## AI Review Layer

When the rule engine returns `AMBIGUOUS` or ambiguity thresholds are hit (borderline credit score, missing documents, borderline income), the request is escalated to the Claude AI agent.

The agent returns:
```json
{
  "recommendation": "APPROVE | REJECT | MANUAL_REVIEW",
  "confidence": 0.82,
  "explanation": "Applicant has borderline credit but strong income-to-loan ratio...",
  "next_step": "Request 6 months of bank statements before final approval."
}
```

- Confidence ≥ 0.75 + APPROVE → auto-approved
- REJECT → auto-rejected
- Low confidence or MANUAL_REVIEW → escalated to human operator

---

## Assignment Requirement Coverage

| Requirement | Implementation |
|---|---|
| Schema validation | Pydantic `LoanRequest` model with field validators |
| Configurable business rules | `config.json` → `engine.py` — no code changes needed |
| Workflow stages | 9 stages in `WorkflowStage` enum |
| Audit logs | Every event timestamped in SQLite `audit_logs` table |
| Idempotency | `Idempotency-Key` header → SQLite uniqueness check |
| External dependency | `external.py` → 30% random failure rate |
| Retry logic | Up to 2 retries → MANUAL_REVIEW on exhaustion |
| AI review for ambiguous | `ai_agent.py` → Claude AI recommendation |
| Decision explanation | `decision_explanation` field in every response |
| Hot-reload config | `POST /config/reload` endpoint |