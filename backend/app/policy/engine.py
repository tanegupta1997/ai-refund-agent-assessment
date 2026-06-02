from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import yaml

# ---------------------------------------------------------------------------
# Rule loading
# ---------------------------------------------------------------------------

_RULES_PATH = Path(__file__).parent / "rules.yaml"

if not _RULES_PATH.exists():
    raise RuntimeError(f"Policy rules file not found: {_RULES_PATH}")

with _RULES_PATH.open() as _f:
    RULES: dict = yaml.safe_load(_f)


def get_rules() -> dict:
    return dict(RULES)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class RefundContext:
    # Customer facts
    customer_id: str
    customer_loyalty_tier: str

    # Order facts
    order_id: str
    order_status: str
    order_date: datetime
    delivery_date: datetime | None
    order_total: float

    # Item facts
    order_item_id: str | None
    product_id: str
    product_name: str
    is_final_sale: bool
    is_refundable_default: bool
    condition_on_arrival: str

    # Request facts
    requested_amount: float
    reason_category: str
    evidence_provided: bool
    evidence_note: str | None

    # Evaluation timestamp — injected by caller, never datetime.now()
    evaluated_at: datetime


@dataclass
class PolicyDecision:
    verdict: str
    reason_codes: list[str]
    primary_reason: str
    approved_amount: float | None
    requires_human: bool
    policy_snapshot: dict


# ---------------------------------------------------------------------------
# Helpers (math only — no rule logic)
# ---------------------------------------------------------------------------


def days_since_delivery(ctx: RefundContext) -> int | None:
    if ctx.delivery_date is None:
        return None
    return (ctx.evaluated_at - ctx.delivery_date).days


def is_within_normal_window(ctx: RefundContext) -> bool:
    days = days_since_delivery(ctx)
    if days is None:
        return False
    return days <= RULES["return_window_days"]


def is_within_extended_window(ctx: RefundContext) -> bool:
    days = days_since_delivery(ctx)
    if days is None:
        return False
    return days <= RULES["defective_extended_window_days"]


# ---------------------------------------------------------------------------
# Policy evaluation
# ---------------------------------------------------------------------------

_NORMAL_WINDOW_REASONS = {"changed_mind", "wrong_item", "never_arrived", "other"}
_EXTENDED_WINDOW_REASONS = {"damaged", "defective"}


def evaluate(ctx: RefundContext) -> PolicyDecision:
    codes: list[str] = []
    snapshot = dict(RULES)

    def _deny(code: str) -> PolicyDecision:
        codes.append(code)
        return PolicyDecision(
            verdict="denied",
            reason_codes=codes,
            primary_reason=code,
            approved_amount=None,
            requires_human=False,
            policy_snapshot=snapshot,
        )

    def _escalate(code: str) -> PolicyDecision:
        codes.append(code)
        return PolicyDecision(
            verdict="escalated",
            reason_codes=codes,
            primary_reason=code,
            approved_amount=None,
            requires_human=True,
            policy_snapshot=snapshot,
        )

    # RULE 1 — Order must be in "delivered" status
    if ctx.order_status != "delivered":
        return _deny("ORDER_NOT_DELIVERED")

    # RULE 2 — A delivery date must be recorded to evaluate the return window
    if ctx.delivery_date is None:
        return _deny("NO_DELIVERY_DATE")

    # RULE 3 — Final sale items are never refundable
    if ctx.is_final_sale:
        return _deny("FINAL_SALE_ITEM")

    # RULE 4 — Return window check (window depends on reason category)
    days = (ctx.evaluated_at - ctx.delivery_date).days
    if ctx.reason_category in _NORMAL_WINDOW_REASONS:
        if days > RULES["return_window_days"]:
            return _deny("OUTSIDE_RETURN_WINDOW")
        else:
            codes.append("WITHIN_RETURN_WINDOW")
    elif ctx.reason_category in _EXTENDED_WINDOW_REASONS:
        if days > RULES["defective_extended_window_days"]:
            return _deny("OUTSIDE_RETURN_WINDOW")
        else:
            codes.append("WITHIN_RETURN_WINDOW")

    # RULE 5 — Product must be refundable by default (final sale already caught)
    if not ctx.is_refundable_default and not ctx.is_final_sale:
        return _deny("PRODUCT_NOT_REFUNDABLE")

    # RULE 6 — Defective/damaged claims require evidence when policy demands it
    if ctx.reason_category in _EXTENDED_WINDOW_REASONS:
        if RULES["defective_requires_evidence"]:
            if not ctx.evidence_provided:
                return _escalate("DEFECTIVE_NO_EVIDENCE")
            else:
                codes.append("DEFECTIVE_WITH_EVIDENCE")

    # RULE 7 — High-value requests must be reviewed by a human
    if ctx.requested_amount > RULES["escalation_threshold_usd"]:
        return _escalate("AMOUNT_EXCEEDS_THRESHOLD")

    # RULE 8 — Requested amount cannot exceed what the customer paid
    if ctx.requested_amount > ctx.order_total:
        return _deny("AMOUNT_EXCEEDS_ORDER_TOTAL")

    # RULE 9 — All checks passed: approve
    codes.append("ALL_CHECKS_PASSED")
    return PolicyDecision(
        verdict="approved",
        reason_codes=codes,
        primary_reason="ALL_CHECKS_PASSED",
        approved_amount=ctx.requested_amount,
        requires_human=False,
        policy_snapshot=snapshot,
    )


__all__ = [
    "RefundContext",
    "PolicyDecision",
    "evaluate",
    "get_rules",
    "RULES",
]
