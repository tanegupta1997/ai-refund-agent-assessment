from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta

import pytest

from app.policy.engine import (
    RULES,
    RefundContext,
    days_since_delivery,
    evaluate,
    is_within_extended_window,
    is_within_normal_window,
)

# ---------------------------------------------------------------------------
# Shared fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def base_ctx() -> RefundContext:
    """Happy-path context — should always approve if unmodified.
    Delivery Jan 5, evaluated Jan 20 = 15 days in (well within 30-day window).
    """
    return RefundContext(
        customer_id="CUST001",
        customer_loyalty_tier="standard",
        order_id="ORD001",
        order_status="delivered",
        order_date=datetime(2024, 1, 1),
        delivery_date=datetime(2024, 1, 5),
        order_total=89.99,
        order_item_id="ITEM001",
        product_id="PROD001",
        product_name="Wireless Headphones",
        is_final_sale=False,
        is_refundable_default=True,
        condition_on_arrival="ok",
        requested_amount=89.99,
        reason_category="changed_mind",
        evidence_provided=False,
        evidence_note=None,
        evaluated_at=datetime(2024, 1, 20),
    )


# ---------------------------------------------------------------------------
# GROUP 1: Baseline
# ---------------------------------------------------------------------------


def test_happy_path_approves(base_ctx):
    decision = evaluate(base_ctx)
    assert decision.verdict == "approved"
    assert decision.approved_amount == 89.99
    assert decision.requires_human is False
    assert "ALL_CHECKS_PASSED" in decision.reason_codes


# ---------------------------------------------------------------------------
# GROUP 2: Order state rules (Rules 1 & 2)
# ---------------------------------------------------------------------------


def test_in_transit_order_denied(base_ctx):
    decision = evaluate(replace(base_ctx, order_status="in_transit"))
    assert decision.verdict == "denied"
    assert "ORDER_NOT_DELIVERED" in decision.reason_codes


def test_cancelled_order_denied(base_ctx):
    decision = evaluate(replace(base_ctx, order_status="cancelled"))
    assert decision.verdict == "denied"
    assert "ORDER_NOT_DELIVERED" in decision.reason_codes


def test_no_delivery_date_denied(base_ctx):
    decision = evaluate(replace(base_ctx, delivery_date=None))
    assert decision.verdict == "denied"
    assert "NO_DELIVERY_DATE" in decision.reason_codes


# ---------------------------------------------------------------------------
# GROUP 3: Final sale (Rule 3)
# ---------------------------------------------------------------------------


def test_final_sale_denied_changed_mind(base_ctx):
    decision = evaluate(replace(base_ctx, is_final_sale=True, reason_category="changed_mind"))
    assert decision.verdict == "denied"
    assert "FINAL_SALE_ITEM" in decision.reason_codes


def test_final_sale_denied_even_defective(base_ctx):
    decision = evaluate(replace(
        base_ctx,
        is_final_sale=True,
        reason_category="defective",
        condition_on_arrival="defective",
        evidence_provided=True,
    ))
    assert decision.verdict == "denied"
    assert "FINAL_SALE_ITEM" in decision.reason_codes


def test_non_final_sale_not_blocked_by_rule3(base_ctx):
    decision = evaluate(replace(base_ctx, is_final_sale=False))
    assert "FINAL_SALE_ITEM" not in decision.reason_codes


# ---------------------------------------------------------------------------
# GROUP 4: Return window (Rule 4)
# ---------------------------------------------------------------------------


def test_exactly_at_window_boundary_approved(base_ctx):
    at_boundary = base_ctx.delivery_date + timedelta(days=RULES["return_window_days"])
    decision = evaluate(replace(base_ctx, evaluated_at=at_boundary))
    assert decision.verdict == "approved"


def test_one_day_outside_window_denied(base_ctx):
    just_outside = base_ctx.delivery_date + timedelta(days=RULES["return_window_days"] + 1)
    decision = evaluate(replace(
        base_ctx,
        evaluated_at=just_outside,
        reason_category="changed_mind",
    ))
    assert decision.verdict == "denied"
    assert "OUTSIDE_RETURN_WINDOW" in decision.reason_codes


def test_within_window_code_recorded(base_ctx):
    inside = base_ctx.delivery_date + timedelta(days=10)
    decision = evaluate(replace(base_ctx, evaluated_at=inside))
    assert "WITHIN_RETURN_WINDOW" in decision.reason_codes


def test_defective_within_extended_window_not_denied_by_window(base_ctx):
    normal_window = RULES["return_window_days"]
    extended_window = RULES["defective_extended_window_days"]
    # 45 days: outside normal (30), inside extended (60)
    days_in = normal_window + 15
    assert days_in < extended_window
    inside_extended = base_ctx.delivery_date + timedelta(days=days_in)
    decision = evaluate(replace(
        base_ctx,
        reason_category="defective",
        condition_on_arrival="defective",
        evidence_provided=True,
        evaluated_at=inside_extended,
    ))
    assert "OUTSIDE_RETURN_WINDOW" not in decision.reason_codes
    assert decision.verdict != "denied"


def test_defective_outside_extended_window_denied(base_ctx):
    outside = base_ctx.delivery_date + timedelta(days=RULES["defective_extended_window_days"] + 1)
    decision = evaluate(replace(
        base_ctx,
        reason_category="defective",
        condition_on_arrival="defective",
        evidence_provided=True,
        evaluated_at=outside,
    ))
    assert decision.verdict == "denied"
    assert "OUTSIDE_RETURN_WINDOW" in decision.reason_codes


def test_changed_mind_uses_normal_window_not_extended(base_ctx):
    # 45 days: outside normal (30) but inside extended (60)
    days_in = RULES["return_window_days"] + 15
    outside_normal = base_ctx.delivery_date + timedelta(days=days_in)
    decision = evaluate(replace(
        base_ctx,
        reason_category="changed_mind",
        evaluated_at=outside_normal,
    ))
    assert decision.verdict == "denied"
    assert "OUTSIDE_RETURN_WINDOW" in decision.reason_codes


# ---------------------------------------------------------------------------
# GROUP 5: Non-refundable product (Rule 5)
# ---------------------------------------------------------------------------


def test_non_refundable_product_denied(base_ctx):
    decision = evaluate(replace(base_ctx, is_refundable_default=False, is_final_sale=False))
    assert decision.verdict == "denied"
    assert "PRODUCT_NOT_REFUNDABLE" in decision.reason_codes


# ---------------------------------------------------------------------------
# GROUP 6: Defective / damaged evidence (Rule 6)
# ---------------------------------------------------------------------------


def test_defective_with_evidence_not_blocked_by_rule6(base_ctx):
    decision = evaluate(replace(
        base_ctx,
        reason_category="defective",
        condition_on_arrival="defective",
        evidence_provided=True,
        evidence_note="Item arrived cracked",
    ))
    assert "DEFECTIVE_NO_EVIDENCE" not in decision.reason_codes
    assert "DEFECTIVE_WITH_EVIDENCE" in decision.reason_codes
    assert decision.verdict == "approved"


def test_defective_without_evidence_escalated(base_ctx):
    decision = evaluate(replace(
        base_ctx,
        reason_category="defective",
        condition_on_arrival="defective",
        evidence_provided=False,
    ))
    assert decision.verdict == "escalated"
    assert "DEFECTIVE_NO_EVIDENCE" in decision.reason_codes
    assert decision.requires_human is True


def test_damaged_without_evidence_escalated(base_ctx):
    decision = evaluate(replace(
        base_ctx,
        reason_category="damaged",
        condition_on_arrival="damaged",
        evidence_provided=False,
    ))
    assert decision.verdict == "escalated"
    assert "DEFECTIVE_NO_EVIDENCE" in decision.reason_codes


def test_changed_mind_skips_evidence_rule(base_ctx):
    decision = evaluate(base_ctx)
    assert "DEFECTIVE_NO_EVIDENCE" not in decision.reason_codes
    assert "DEFECTIVE_WITH_EVIDENCE" not in decision.reason_codes


# ---------------------------------------------------------------------------
# GROUP 7: Amount escalation threshold (Rule 7)
# ---------------------------------------------------------------------------


def test_amount_exactly_at_threshold_approved(base_ctx):
    threshold = RULES["escalation_threshold_usd"]
    decision = evaluate(replace(base_ctx, requested_amount=float(threshold), order_total=float(threshold)))
    assert decision.verdict == "approved"


def test_amount_one_cent_over_threshold_escalated(base_ctx):
    threshold = RULES["escalation_threshold_usd"]
    decision = evaluate(replace(base_ctx, requested_amount=threshold + 0.01, order_total=threshold + 100))
    assert decision.verdict == "escalated"
    assert "AMOUNT_EXCEEDS_THRESHOLD" in decision.reason_codes
    assert decision.requires_human is True


def test_high_value_escalation_beats_approval(base_ctx):
    decision = evaluate(replace(
        base_ctx,
        requested_amount=1299.99,
        order_total=1299.99,
        is_final_sale=False,
        is_refundable_default=True,
        order_status="delivered",
    ))
    assert decision.verdict == "escalated"
    assert "AMOUNT_EXCEEDS_THRESHOLD" in decision.reason_codes
    assert decision.approved_amount is None


# ---------------------------------------------------------------------------
# GROUP 8: Amount sanity check (Rule 8)
# ---------------------------------------------------------------------------


def test_amount_exceeds_order_total_denied(base_ctx):
    decision = evaluate(replace(base_ctx, requested_amount=200.00, order_total=89.99))
    assert decision.verdict == "denied"
    assert "AMOUNT_EXCEEDS_ORDER_TOTAL" in decision.reason_codes


def test_amount_equal_to_order_total_ok(base_ctx):
    decision = evaluate(replace(base_ctx, requested_amount=89.99, order_total=89.99))
    assert "AMOUNT_EXCEEDS_ORDER_TOTAL" not in decision.reason_codes


# ---------------------------------------------------------------------------
# GROUP 9: Rule ordering — short-circuit verification
# ---------------------------------------------------------------------------


def test_final_sale_fires_before_window_check(base_ctx):
    inside_window = base_ctx.delivery_date + timedelta(days=5)
    decision = evaluate(replace(base_ctx, is_final_sale=True, evaluated_at=inside_window))
    assert "FINAL_SALE_ITEM" in decision.reason_codes
    assert "OUTSIDE_RETURN_WINDOW" not in decision.reason_codes


def test_not_delivered_fires_before_final_sale(base_ctx):
    decision = evaluate(replace(base_ctx, order_status="in_transit", is_final_sale=True))
    assert "ORDER_NOT_DELIVERED" in decision.reason_codes
    assert "FINAL_SALE_ITEM" not in decision.reason_codes


def test_denial_beats_escalation(base_ctx):
    decision = evaluate(replace(
        base_ctx,
        is_final_sale=True,
        requested_amount=999.99,
        order_total=999.99,
    ))
    assert decision.verdict == "denied"


# ---------------------------------------------------------------------------
# GROUP 10: Policy snapshot & auditability
# ---------------------------------------------------------------------------


def test_policy_snapshot_included_in_decision(base_ctx):
    decision = evaluate(base_ctx)
    assert decision.policy_snapshot is not None
    assert "return_window_days" in decision.policy_snapshot
    assert "escalation_threshold_usd" in decision.policy_snapshot
    assert decision.policy_snapshot["return_window_days"] == RULES["return_window_days"]


def test_policy_snapshot_is_a_copy_not_reference(base_ctx):
    decision = evaluate(base_ctx)
    decision.policy_snapshot["return_window_days"] = 999
    second = evaluate(base_ctx)
    assert second.policy_snapshot["return_window_days"] == RULES["return_window_days"]


def test_reason_codes_always_a_list(base_ctx):
    decision = evaluate(base_ctx)
    assert isinstance(decision.reason_codes, list)


def test_primary_reason_is_in_reason_codes(base_ctx):
    decision = evaluate(base_ctx)
    assert decision.primary_reason in decision.reason_codes


# ---------------------------------------------------------------------------
# GROUP 11: Helper functions
# ---------------------------------------------------------------------------


def test_days_since_delivery_correct(base_ctx):
    ctx = replace(base_ctx, delivery_date=datetime(2024, 1, 5), evaluated_at=datetime(2024, 1, 20))
    assert days_since_delivery(ctx) == 15


def test_days_since_delivery_no_date_returns_none(base_ctx):
    ctx = replace(base_ctx, delivery_date=None)
    assert days_since_delivery(ctx) is None


def test_is_within_normal_window_true(base_ctx):
    ctx = replace(base_ctx, evaluated_at=base_ctx.delivery_date + timedelta(days=29))
    assert is_within_normal_window(ctx) is True


def test_is_within_normal_window_false(base_ctx):
    ctx = replace(base_ctx, evaluated_at=base_ctx.delivery_date + timedelta(days=31))
    assert is_within_normal_window(ctx) is False


def test_is_within_extended_window_true(base_ctx):
    ctx = replace(base_ctx, evaluated_at=base_ctx.delivery_date + timedelta(days=59))
    assert is_within_extended_window(ctx) is True
