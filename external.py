"""
external.py — Simulated external credit bureau dependency.

Randomly fails ~30% of the time to demonstrate retry + failure handling.
In a real system this would be an HTTP call to a third-party API.
"""

import random
import time


class ExternalServiceError(Exception):
    """Raised when the simulated credit bureau call fails."""
    pass


def check_credit(request_id: str, credit_score: int) -> dict:
    """
    Simulate a call to an external credit bureau.

    Failures:
      - 30% chance of timeout → raises ExternalServiceError
      - On success, returns a slightly varied verified score (bureau noise)

    Args:
        request_id:   Used to log which loan request triggered this call.
        credit_score: The applicant's self-reported score.

    Returns:
        dict with verified_credit_score, bureau name, flags, etc.
    """
    time.sleep(0.05)   # simulate network latency (short for demo)

    if random.random() < 0.30:
        raise ExternalServiceError(
            f"SimulatedCreditBureau: request timeout for request_id={request_id}"
        )

    # Bureaus add slight variance to reported scores
    noise = random.randint(-25, 25)
    verified = max(300, min(850, credit_score + noise))

    flags = []
    if verified < 580:
        flags.append("HIGH_RISK")
    elif verified < 650:
        flags.append("MODERATE_RISK")
    if credit_score - verified > 30:
        flags.append("SCORE_DISCREPANCY")

    return {
        "bureau":                "SimulatedCreditBureau v2",
        "request_id":            request_id,
        "self_reported_score":   credit_score,
        "verified_credit_score": verified,
        "report_status":         "COMPLETE",
        "flags":                 flags,
    }