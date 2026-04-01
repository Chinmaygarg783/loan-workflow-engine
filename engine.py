"""
engine.py — Deterministic rule evaluator.

Rules are loaded from config.json. No code changes required to add/modify rules.
"""

import os
import json
from typing import Tuple, List

from models import LoanRequest


# ── Config loader ──────────────────────────────────────────────────────────────
def load_config(path: str = None) -> dict:
    if path is None:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
    with open(path) as f:
        return json.load(f)


# ── Field helpers ──────────────────────────────────────────────────────────────
def _get_field_value(data: LoanRequest, rule: dict) -> float:
    """Resolve a rule's field, including derived (computed) fields."""
    if rule.get("derived"):
        if rule["field"] == "loan_to_income":
            return data.loan_amount / data.income
        raise ValueError(f"Unknown derived field: {rule['field']}")
    return float(getattr(data, rule["field"]))


def _check_condition(value: float, operator: str, threshold: float) -> bool:
    ops = {
        "lt":  lambda a, b: a < b,
        "lte": lambda a, b: a <= b,
        "gt":  lambda a, b: a > b,
        "gte": lambda a, b: a >= b,
        "eq":  lambda a, b: a == b,
        "neq": lambda a, b: a != b,
    }
    if operator not in ops:
        raise ValueError(f"Unknown operator: {operator}")
    return ops[operator](value, threshold)


# ── Core evaluation ────────────────────────────────────────────────────────────
def evaluate_rules(data: LoanRequest, rules: list) -> Tuple[str, List[dict]]:
    """
    Evaluate all configured rules against the request.

    Returns:
        (decision, triggered_rules)
        decision ∈ {"APPROVE", "REJECT", "AMBIGUOUS"}
    """
    triggered: List[dict] = []
    has_approval = False

    for rule in sorted(rules, key=lambda r: r.get("priority", 99)):
        try:
            value = _get_field_value(data, rule)
            if _check_condition(value, rule["operator"], rule["value"]):
                entry = {
                    "rule_id":     rule["id"],
                    "name":        rule["name"],
                    "description": rule["description"],
                    "action":      rule["action"],
                    "field":       rule["field"],
                    "field_value": round(value, 4),
                }
                triggered.append(entry)

                if rule["action"] == "REJECT":
                    return "REJECT", triggered          # first rejection wins
                elif rule["action"] == "APPROVE":
                    has_approval = True
        except Exception:
            continue                                     # skip broken rules gracefully

    if has_approval:
        return "APPROVE", triggered

    return "AMBIGUOUS", triggered


# ── Ambiguity detection ────────────────────────────────────────────────────────
def is_ambiguous(data: LoanRequest, config: dict) -> Tuple[bool, str]:
    """
    Check whether a case should be escalated to the AI review agent.
    Returns (is_ambiguous, human_readable_reason).
    """
    t = config["workflow"]["ambiguous_thresholds"]
    reasons: List[str] = []

    cs = data.credit_score
    if t["credit_score_min"] <= cs <= t["credit_score_max"]:
        reasons.append(
            f"Borderline credit score {cs} (ambiguous range: {t['credit_score_min']}–{t['credit_score_max']})"
        )

    if t["income_min"] <= data.income <= t["income_max"]:
        reasons.append(
            f"Borderline annual income ${data.income:,.0f} (range: ${t['income_min']:,}–${t['income_max']:,})"
        )

    if not data.documents_submitted:
        reasons.append("Required documents were not submitted")

    if reasons:
        return True, "; ".join(reasons)
    return False, ""