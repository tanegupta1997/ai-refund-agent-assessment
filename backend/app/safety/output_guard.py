from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FORBIDDEN_TERMS: list[str] = [
    "policy engine",
    "reason_code",
    "reason code",
    "engine.evaluate",
    "ALL_CHECKS_PASSED",
    "FINAL_SALE_ITEM",
    "OUTSIDE_RETURN_WINDOW",
    "AMOUNT_EXCEEDS_THRESHOLD",
    "DEFECTIVE_NO_EVIDENCE",
    "escalation_threshold",
    "return_window_days",
    "tool_call",
    "langgraph",
    "agent state",
    "injection",
    "prompt injection",
    "RefundContext",
    "PolicyDecision",
    "order_item_id",
    "product_id",
]

VERDICT_SIGNAL_WORDS: dict[str, list[str]] = {
    "approved": [
        "approved",
        "approve",
        "refund will be processed",
        "will receive",
        "processed",
        "issued",
    ],
    "denied": [
        "unable to process",
        "cannot process",
        "not eligible",
        "denied",
        "unfortunately",
        "does not qualify",
        "cannot be refunded",
    ],
    "escalated": [
        "human",
        "team",
        "review",
        "specialist",
        "follow up",
        "escalated",
        "1-2 business days",
    ],
}

_AMOUNT_RE = re.compile(r"\$([\d,]+\.?\d*)")

_BLOCKING_VIOLATIONS = {"VERDICT_MISMATCH", "FORBIDDEN_TERM", "EMPTY_RESPONSE", "AMOUNT_MISMATCH"}


# ---------------------------------------------------------------------------
# Data class
# ---------------------------------------------------------------------------


@dataclass
class GuardResult:
    safe: bool
    text: str
    violations: list[str] = field(default_factory=list)
    was_replaced: bool = False


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------


def validate_response(
    response_text: str | None,
    expected_verdict: str,
    expected_amount: float | None,
) -> GuardResult:
    try:
        violations: list[str] = []

        # CHECK 1 — Empty response
        if not response_text or len(response_text.strip()) < 10:
            violations.append("EMPTY_RESPONSE")
            fallback = get_safe_fallback(expected_verdict, expected_amount)
            return GuardResult(safe=False, text=fallback, violations=violations, was_replaced=True)

        text_lower = response_text.lower()

        # CHECK 2 — Forbidden terms
        found_forbidden: list[str] = []
        for term in FORBIDDEN_TERMS:
            if term.lower() in text_lower:
                found_forbidden.append(term)
        if found_forbidden:
            logger.warning("Output guard: forbidden terms found: %s", found_forbidden)
            violations.append("FORBIDDEN_TERM")

        # CHECK 3 — Verdict signal cross-check
        correct_signals = VERDICT_SIGNAL_WORDS.get(expected_verdict, [])
        has_correct = any(s.lower() in text_lower for s in correct_signals)

        wrong_verdicts = [v for v in VERDICT_SIGNAL_WORDS if v != expected_verdict]
        wrong_signals_found: list[str] = []
        for wrong_verdict in wrong_verdicts:
            for signal in VERDICT_SIGNAL_WORDS[wrong_verdict]:
                if signal.lower() in text_lower:
                    wrong_signals_found.append(signal)

        if wrong_signals_found and not has_correct:
            logger.warning(
                "Output guard: verdict mismatch — expected=%s, wrong signals=%s",
                expected_verdict,
                wrong_signals_found,
            )
            violations.append("VERDICT_MISMATCH")
        elif wrong_signals_found and has_correct:
            logger.warning(
                "Output guard: mixed verdict signals — expected=%s, also saw=%s",
                expected_verdict,
                wrong_signals_found,
            )

        # CHECK 4 — Amount hallucination (approved only)
        if expected_verdict == "approved" and expected_amount is not None:
            amount_matches = _AMOUNT_RE.findall(response_text)
            for raw in amount_matches:
                parsed = float(raw.replace(",", ""))
                if abs(parsed - expected_amount) > 0.01:
                    logger.warning(
                        "Output guard: amount mismatch — expected=%.2f, found=%.2f",
                        expected_amount,
                        parsed,
                    )
                    violations.append("AMOUNT_MISMATCH")
                    break

        # CHECK 5 — Minimum length
        if len(response_text.split()) < 5:
            violations.append("RESPONSE_TOO_SHORT")

        is_safe = not any(v in _BLOCKING_VIOLATIONS for v in violations)

        if is_safe:
            return GuardResult(safe=True, text=response_text, violations=violations, was_replaced=False)

        fallback = get_safe_fallback(expected_verdict, expected_amount)
        logger.warning("Output guard: unsafe response — violations=%s, using fallback", violations)
        return GuardResult(safe=False, text=fallback, violations=violations, was_replaced=True)

    except Exception as exc:
        logger.error("validate_response error: %s", exc)
        fallback = get_safe_fallback(expected_verdict, expected_amount)
        return GuardResult(safe=False, text=fallback, violations=["GUARD_ERROR"], was_replaced=True)


def get_safe_fallback(verdict: str, approved_amount: float | None) -> str:
    if verdict == "approved":
        amount_str = f"${approved_amount:.2f}" if approved_amount is not None else "the requested amount"
        return (
            f"Your refund of {amount_str} has been approved. "
            "Please allow 3-5 business days for processing."
        )
    if verdict == "denied":
        return (
            "After reviewing your request, we're unable to process this refund. "
            "Please contact our support team if you have further questions."
        )
    if verdict == "escalated":
        return (
            "Your refund request has been received and will be reviewed by our team "
            "within 1-2 business days. We'll be in touch shortly."
        )
    return "Thank you for contacting support. A member of our team will follow up with you shortly."


__all__ = [
    "GuardResult",
    "validate_response",
    "get_safe_fallback",
    "FORBIDDEN_TERMS",
    "VERDICT_SIGNAL_WORDS",
]
