from __future__ import annotations

import numpy as np


def sample_payment_delay(risk_score: float, scale: float = 5.0) -> float:
    """Gamma-distributed payment delay in days. shape = 1 + risk_score * 2."""
    shape = 1.0 + risk_score * 2.0
    return float(np.random.gamma(shape=shape, scale=scale))


def compute_success_probability(risk_score: float) -> float:
    if risk_score < 0.3:
        return 0.95
    if risk_score < 0.7:
        return 0.70
    return 0.40


def attempt_payment(risk_score: float) -> bool:
    """Return True if payment succeeds."""
    import random
    prob = compute_success_probability(risk_score)
    return random.random() < prob


def apply_payment(invoice_balance: float, payment_amount: float) -> float:
    """PAY-01: never capture more than the outstanding balance."""
    return min(invoice_balance, payment_amount)
