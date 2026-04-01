from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Dict, Any
from enum import Enum


class WorkflowStage(str, Enum):
    RECEIVED = "RECEIVED"
    VALIDATED = "VALIDATED"
    RULES_EVALUATED = "RULES_EVALUATED"
    EXTERNAL_CHECK_PENDING = "EXTERNAL_CHECK_PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    MANUAL_REVIEW = "MANUAL_REVIEW"
    RETRY_SCHEDULED = "RETRY_SCHEDULED"
    FAILED = "FAILED"


class LoanRequest(BaseModel):
    request_id: str = Field(..., description="Unique identifier for this request")
    name: str = Field(..., min_length=1)
    age: int = Field(..., ge=0, le=120)
    income: float = Field(..., gt=0, description="Annual income in USD")
    loan_amount: float = Field(..., gt=0, description="Requested loan amount in USD")
    credit_score: int = Field(..., ge=300, le=850)
    documents_submitted: bool = Field(..., description="Whether all required documents were submitted")

    @field_validator("loan_amount")
    @classmethod
    def loan_must_be_positive(cls, v):
        if v <= 0:
            raise ValueError("Loan amount must be positive")
        return v


class AuditEvent(BaseModel):
    timestamp: str
    stage: str
    event: str
    details: Dict[str, Any] = {}


class AIReview(BaseModel):
    recommendation: str          # APPROVE | REJECT | MANUAL_REVIEW
    confidence: float             # 0.0 – 1.0
    explanation: str
    next_step: str


class WorkflowState(BaseModel):
    request_id: str
    idempotency_key: str
    data: LoanRequest
    current_stage: WorkflowStage
    retry_count: int = 0
    audit_trail: List[AuditEvent] = []
    ai_review: Optional[AIReview] = None
    final_decision: Optional[str] = None
    decision_explanation: Optional[str] = None
    created_at: str
    updated_at: str