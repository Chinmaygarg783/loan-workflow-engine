"""
ai_agent.py — AI-assisted review for ambiguous loan applications.

Called only when the deterministic rule engine returns AMBIGUOUS
or ambiguity thresholds are triggered (borderline score, missing docs, etc.).

Uses OpenRouter with GPT-4o mini via the OpenAI-compatible SDK.
Requires: OPENROUTER_API_KEY environment variable.
"""

import os
import json
from openai import OpenAI

from models import LoanRequest, AIReview

_client = None

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
MODEL = "openai/gpt-4o-mini"


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        api_key = "your-openrouter-api-key-here"echo "workflow.db" > .gitignore
echo "__pycache__/" >> .gitignore
echo "*.pyc" >> .gitignore
echo "*.db" >> .gitignore
            raise RuntimeError(
                "OPENROUTER_API_KEY environment variable is not set. "
                "Export it before running: export OPENROUTER_API_KEY=sk-or-..."
            )
        _client = OpenAI(
            api_key=api_key,
            base_url=OPENROUTER_BASE_URL,
        )
    return _client


SYSTEM_PROMPT = """You are an expert loan underwriting AI assistant working for a responsible lender.

Your task is to review borderline or ambiguous loan applications that the automated rule engine could not 
decisively approve or reject. You must weigh risk carefully and provide a structured recommendation.

IMPORTANT: You must respond with ONLY a valid JSON object — no preamble, no markdown, no explanation outside the JSON.

Required JSON format:
{
  "recommendation": "APPROVE" | "REJECT" | "MANUAL_REVIEW",
  "confidence": <float 0.0–1.0>,
  "explanation": "<clear 1–3 sentence reasoning>",
  "next_step": "<concrete actionable step for the operations team>"
}

Guidelines:
- APPROVE only if confidence >= 0.75 and evidence supports repayment capacity.
- REJECT when risk clearly outweighs benefit.
- MANUAL_REVIEW when you are genuinely uncertain or key information is missing.
- Consider: debt-to-income ratio, credit score context, document completeness, income stability signals.
- Be conservative — false approvals are more costly than false rejects."""


def ai_review(data: LoanRequest, ambiguity_context: str) -> AIReview:
    """
    Ask the AI agent to review an ambiguous loan application.

    Args:
        data:               The full loan request.
        ambiguity_context:  Human-readable string explaining why it was flagged.

    Returns:
        AIReview with recommendation, confidence, explanation, next_step.
    """
    client = _get_client()

    lti_ratio = data.loan_amount / data.income

    user_message = f"""Please review the following ambiguous loan application:

--- APPLICANT DETAILS ---
Name:                 {data.name}
Age:                  {data.age} years
Annual Income:        ${data.income:,.2f}
Requested Loan:       ${data.loan_amount:,.2f}
Loan-to-Income Ratio: {lti_ratio:.2f}x
Credit Score:         {data.credit_score} / 850
Documents Submitted:  {"Yes" if data.documents_submitted else "No - MISSING"}

--- WHY THIS WAS FLAGGED ---
{ambiguity_context}

--- YOUR TASK ---
Provide your underwriting recommendation as a JSON object."""

    response = client.chat.completions.create(
        model=MODEL,
        max_tokens=512,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": user_message},
        ],
    )

    raw = response.choices[0].message.content.strip()

    # Strip accidental markdown fences
    if raw.startswith("```"):
        parts = raw.split("```")
        raw = parts[1].lstrip("json").strip() if len(parts) > 1 else raw

    parsed = json.loads(raw)

    return AIReview(
        recommendation=parsed["recommendation"],
        confidence=float(parsed["confidence"]),
        explanation=parsed["explanation"],
        next_step=parsed["next_step"],
    )