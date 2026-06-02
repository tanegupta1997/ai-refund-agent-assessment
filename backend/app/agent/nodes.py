from __future__ import annotations

import dataclasses
import logging
import time
from datetime import datetime, timezone
from typing import NotRequired, TypedDict

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

from app.safety.injection import check_for_injection
from app.safety.output_guard import validate_response

# LLM — importable even when OPENAI_API_KEY is absent (tests, CI)
try:
    from app.agent.llm import call_llm_for_json as _call_llm_for_json
    from app.agent.llm import call_llm_for_text as _call_llm_for_text
except RuntimeError:
    def _call_llm_for_json(prompt: str, system_prompt: str | None = None) -> dict | None:  # type: ignore[misc]
        return None
    def _call_llm_for_text(prompt: str, system_prompt: str | None = None) -> str | None:  # type: ignore[misc]
        return None

from app.agent.prompts import (
    SYSTEM_PROMPT,
    build_clarification_prompt,
    build_composition_prompt,
    build_deflection_prompt,
    build_intent_extraction_prompt,
    get_policy_explanation_hints,
)
from app.agent.tools import (
    build_refund_context,
    get_order_detail,
    get_orders_for_customer,
    lookup_customer,
)
from app.db.models import AgentLog, RefundRequest
from app.policy.engine import RefundContext, evaluate

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_VALID_REASON_CATEGORIES = frozenset(
    {"changed_mind", "damaged", "defective", "never_arrived", "wrong_item", "other"}
)

_APPROVED_FALLBACK = (
    "Your refund of ${amount:.2f} for order {order_id} has been approved. "
    "Please allow 3-5 business days for processing."
)
_DENIED_FALLBACK = (
    "After reviewing your request for order {order_id}, we're unable to process "
    "this refund. Please contact support if you have questions."
)
_ESCALATED_FALLBACK = (
    "Your refund request for order {order_id} has been logged and will be "
    "reviewed by our team within 1-2 business days."
)
_DEFLECTION_FALLBACK = (
    "I'm here to help with refund requests. "
    "Could you describe the issue with your order?"
)


# ---------------------------------------------------------------------------
# AgentState
# ---------------------------------------------------------------------------


class AgentState(TypedDict):
    # Always present at graph entry
    conversation_id: str
    user_message: str
    conversation_history: list[dict]

    # Identity resolution
    customer_id: NotRequired[str | None]
    customer_name: NotRequired[str | None]
    customer_data: NotRequired[dict | None]

    # Order resolution
    order_id: NotRequired[str | None]
    order_data: NotRequired[dict | None]
    order_item_id: NotRequired[str | None]

    # Parsed intent
    parsed_intent: NotRequired[dict | None]
    needs_clarification: NotRequired[bool]
    clarification_question: NotRequired[str | None]
    is_refund_request: NotRequired[bool]

    # Refund details
    requested_amount: NotRequired[float | None]
    reason_category: NotRequired[str | None]
    evidence_provided: NotRequired[bool]
    evidence_note: NotRequired[str | None]

    # Policy evaluation
    refund_context: NotRequired[dict | None]
    policy_decision: NotRequired[dict | None]
    verdict: NotRequired[str | None]

    # Safety
    injection_detected: NotRequired[bool]
    injection_flags: NotRequired[list[str]]

    # Tool call log
    tool_calls_log: NotRequired[list[dict]]

    # Output
    final_response: NotRequired[str | None]
    refund_request_id: NotRequired[str | None]

    # Routing
    error_message: NotRequired[str | None]
    current_node: NotRequired[str]

    # Timing
    start_time: NotRequired[float | None]


# ---------------------------------------------------------------------------
# Datetime helpers
# ---------------------------------------------------------------------------


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _serialize_context(ctx: RefundContext) -> dict:
    d = dataclasses.asdict(ctx)
    for key in ("order_date", "delivery_date", "evaluated_at"):
        if d.get(key) is not None and isinstance(d[key], datetime):
            d[key] = d[key].isoformat()
    return d


def _deserialize_context(d: dict) -> RefundContext:
    d = dict(d)
    for key in ("order_date", "delivery_date", "evaluated_at"):
        val = d.get(key)
        if val and isinstance(val, str):
            d[key] = datetime.fromisoformat(val)
    return RefundContext(**d)


# ---------------------------------------------------------------------------
# NODE 0 — safety_check_node
# ---------------------------------------------------------------------------


def safety_check_node(state: AgentState) -> dict:
    result = check_for_injection(state["user_message"])
    detected: bool = result.detected
    flags: list[str] = result.flags
    if detected:
        logger.warning("Injection detected — flags: %s", flags)
    return {
        "injection_detected": detected,
        "injection_flags": flags,
        "start_time": time.time(),
        "current_node": "safety_check",
    }


# ---------------------------------------------------------------------------
# NODE 1 — intent_extraction_node
# ---------------------------------------------------------------------------


def intent_extraction_node(state: AgentState) -> dict:
    if state.get("injection_detected"):
        return {
            "parsed_intent": None,
            "needs_clarification": False,
            "is_refund_request": False,
            "current_node": "intent_extraction",
        }

    prompt = build_intent_extraction_prompt(
        state["user_message"],
        state.get("conversation_history", []),
    )
    parsed = _call_llm_for_json(prompt, SYSTEM_PROMPT)

    if parsed is None or "is_refund_request" not in parsed or "needs_clarification" not in parsed:
        return {
            "error_message": "Failed to parse your request. Please rephrase and try again.",
            "needs_clarification": True,
            "current_node": "intent_extraction",
        }

    raw_reason = parsed.get("reason_category")
    if raw_reason and raw_reason not in _VALID_REASON_CATEGORIES:
        raw_reason = "other"

    requested = parsed.get("requested_amount")
    try:
        requested = float(requested) if requested is not None else None
    except (TypeError, ValueError):
        requested = None

    return {
        "parsed_intent": parsed,
        "is_refund_request": bool(parsed.get("is_refund_request")),
        "needs_clarification": bool(parsed.get("needs_clarification")),
        "clarification_question": parsed.get("clarification_question"),
        "reason_category": raw_reason,
        "requested_amount": requested,
        "evidence_provided": bool(parsed.get("evidence_provided", False)),
        "evidence_note": parsed.get("evidence_claim"),
        "current_node": "intent_extraction",
    }


# ---------------------------------------------------------------------------
# NODE 2 — identity_resolution_node
# ---------------------------------------------------------------------------


def identity_resolution_node(state: AgentState, db: Session) -> dict:
    tool_log: list[dict] = list(state.get("tool_calls_log") or [])

    intent = state.get("parsed_intent") or {}
    identifier = intent.get("customer_identifier")

    if not identifier:
        return {
            "needs_clarification": True,
            "clarification_question": "Could you please provide your email address or customer ID?",
            "current_node": "identity_resolution",
        }

    cust_result = lookup_customer(db, identifier)
    customer_data: dict = cust_result.data if cust_result.success and cust_result.data else {}
    tool_log.append({
        "tool": "lookup_customer",
        "args": {"identifier": identifier},
        "result_summary": (
            f"found customer {customer_data.get('customer_id', '?')}"
            if cust_result.success else "not found"
        ),
    })

    if not cust_result.success:
        return {
            "error_message": cust_result.error,
            "needs_clarification": True,
            "clarification_question": "We couldn't find an account with that email. Could you double-check?",
            "tool_calls_log": tool_log,
            "current_node": "identity_resolution",
        }

    customer_id: str = customer_data.get("customer_id", "")
    customer_name: str = customer_data.get("name", "")

    update: dict = {
        "customer_id": customer_id,
        "customer_name": customer_name,
        "customer_data": customer_data,
        "tool_calls_log": tool_log,
    }

    order_ref = intent.get("order_reference")
    if order_ref:
        order_result = get_order_detail(db, order_ref, customer_id)
        tool_log.append({
            "tool": "get_order_detail",
            "args": {"order_id": order_ref, "customer_id": customer_id},
            "result_summary": f"found order {order_ref}" if order_result.success else order_result.error,
        })
        if order_result.success and order_result.data:
            update["order_id"] = order_result.data["order_id"]
            update["order_data"] = order_result.data
        else:
            logger.warning("Order lookup failed: %s", order_result.error)
    else:
        orders_result = get_orders_for_customer(db, customer_id)
        orders_data: list[dict] = orders_result.data if orders_result.success and orders_result.data else []
        tool_log.append({
            "tool": "get_orders_for_customer",
            "args": {"customer_id": customer_id},
            "result_summary": f"{len(orders_data)} orders" if orders_result.success else "error",
        })
        if not orders_result.success:
            update["error_message"] = orders_result.error
        elif len(orders_data) == 0:
            update["error_message"] = "No orders found for this account."
        elif len(orders_data) == 1:
            detail = get_order_detail(db, orders_data[0]["order_id"], customer_id)
            if detail.success and detail.data:
                update["order_id"] = detail.data["order_id"]
                update["order_data"] = detail.data
        else:
            order_ids = ", ".join(o["order_id"] for o in orders_data)
            update["needs_clarification"] = True
            update["clarification_question"] = (
                f"We found multiple orders on your account ({order_ids}). "
                "Which order would you like to request a refund for?"
            )

    update["tool_calls_log"] = tool_log
    update["current_node"] = "identity_resolution"
    return update


# ---------------------------------------------------------------------------
# NODE 3 — context_assembly_node
# ---------------------------------------------------------------------------


def context_assembly_node(state: AgentState, db: Session) -> dict:
    tool_log: list[dict] = list(state.get("tool_calls_log") or [])

    missing_checks = [
        ("customer_id", "Could you please provide your customer email or ID?"),
        ("order_id", "Which order would you like to request a refund for?"),
        ("reason_category", "What is the reason for your refund request?"),
        ("requested_amount", "What amount would you like refunded?"),
    ]
    for field, question in missing_checks:
        if not state.get(field):
            return {
                "needs_clarification": True,
                "clarification_question": question,
                "current_node": "context_assembly",
            }

    order_data = state.get("order_data") or {}
    items: list[dict] = order_data.get("items", [])
    order_item_id: str | None = state.get("order_item_id")

    if not order_item_id:
        if len(items) == 1:
            order_item_id = str(items[0]["order_item_id"])
        elif len(items) > 1:
            item_ids = ", ".join(i["order_item_id"] for i in items)
            return {
                "needs_clarification": True,
                "clarification_question": (
                    f"This order has multiple items ({item_ids}). "
                    "Which item would you like to refund?"
                ),
                "current_node": "context_assembly",
            }
        else:
            return {
                "error_message": "No order items found for this order.",
                "current_node": "context_assembly",
            }

    customer_id: str = state.get("customer_id") or ""
    order_id: str = state.get("order_id") or ""
    requested_amount: float = state.get("requested_amount") or 0.0
    reason_category: str = state.get("reason_category") or "other"

    ctx_result = build_refund_context(
        db=db,
        customer_id=customer_id,
        order_id=order_id,
        order_item_id=order_item_id,
        requested_amount=requested_amount,
        reason_category=reason_category,
        evidence_provided=state.get("evidence_provided", False),
        evidence_note=state.get("evidence_note"),
        evaluated_at=_utcnow(),
    )
    tool_log.append({
        "tool": "build_refund_context",
        "args": {
            "customer_id": customer_id,
            "order_id": order_id,
            "order_item_id": order_item_id,
        },
        "result_summary": "context built" if ctx_result.success else ctx_result.error,
    })

    if not ctx_result.success or ctx_result.data is None:
        return {
            "error_message": ctx_result.error,
            "tool_calls_log": tool_log,
            "current_node": "context_assembly",
        }

    return {
        "refund_context": _serialize_context(ctx_result.data),
        "order_item_id": order_item_id,
        "tool_calls_log": tool_log,
        "current_node": "context_assembly",
    }


# ---------------------------------------------------------------------------
# NODE 4 — policy_evaluation_node
# ---------------------------------------------------------------------------


def policy_evaluation_node(state: AgentState) -> dict:
    try:
        raw_ctx = state.get("refund_context")
        if not raw_ctx:
            raise ValueError("refund_context is missing from state")
        ctx = _deserialize_context(raw_ctx)
        decision = evaluate(ctx)
        return {
            "policy_decision": dataclasses.asdict(decision),
            "verdict": decision.verdict,
            "current_node": "policy_evaluation",
        }
    except Exception as exc:
        logger.critical("Policy evaluation error: %s", exc, exc_info=True)
        return {
            "verdict": "escalated",
            "error_message": "Policy evaluation error — escalating for human review",
            "current_node": "policy_evaluation",
        }


# ---------------------------------------------------------------------------
# NODE 5 — response_composition_node
# ---------------------------------------------------------------------------


def response_composition_node(state: AgentState, db: Session) -> dict:
    policy_decision: dict = state.get("policy_decision") or {}
    verdict: str = state.get("verdict") or "escalated"
    order_id: str = state.get("order_id") or "your order"

    # STEP A — Write RefundRequest to DB
    refund_request_id: str | None = None
    try:
        req = RefundRequest(
            customer_id=state.get("customer_id") or "",
            order_id=state.get("order_id") or "",
            order_item_id=state.get("order_item_id"),
            requested_amount=state.get("requested_amount") or 0.0,
            reason_category=state.get("reason_category") or "other",
            evidence_provided=state.get("evidence_provided", False),
            evidence_note=state.get("evidence_note"),
            decision=verdict,
            decision_reasons=policy_decision.get("reason_codes"),
            decided_at=_utcnow(),
        )
        db.add(req)
        db.commit()
        db.refresh(req)
        refund_request_id = req.refund_request_id
    except Exception as exc:
        logger.error("Failed to write RefundRequest: %s", exc, exc_info=True)
        try:
            db.rollback()
        except Exception:
            pass

    # STEP B — Build composition prompt
    order_data = state.get("order_data") or {}
    items: list[dict] = order_data.get("items", [])
    product_name = items[0]["product_name"] if items else "your item"

    hints = get_policy_explanation_hints()
    prompt = build_composition_prompt(
        verdict=verdict,
        reason_codes=policy_decision.get("reason_codes", []),
        primary_reason=policy_decision.get("primary_reason", ""),
        approved_amount=policy_decision.get("approved_amount"),
        requested_amount=state.get("requested_amount") or 0.0,
        customer_name=state.get("customer_name") or "there",
        product_name=product_name,
        order_id=order_id,
        policy_explanation_hints=hints,
    )

    # STEP C — Call LLM for text
    response_text = _call_llm_for_text(prompt, SYSTEM_PROMPT)

    # STEP D — Output guard
    if response_text:
        guard_result = validate_response(
            response_text=response_text,
            expected_verdict=verdict,
            expected_amount=policy_decision.get("approved_amount"),
        )
        if guard_result.safe:
            final_response = guard_result.text
        else:
            logger.warning("Output guard fired for verdict=%s — using fallback", verdict)
            final_response = _build_fallback(verdict, state.get("requested_amount"), order_id)
    else:
        final_response = _build_fallback(verdict, state.get("requested_amount"), order_id)

    return {
        "final_response": final_response,
        "refund_request_id": refund_request_id,
        "current_node": "response_composition",
    }


def _build_fallback(verdict: str, amount: float | None, order_id: str) -> str:
    if verdict == "approved":
        return _APPROVED_FALLBACK.format(amount=amount or 0.0, order_id=order_id)
    if verdict == "denied":
        return _DENIED_FALLBACK.format(order_id=order_id)
    return _ESCALATED_FALLBACK.format(order_id=order_id)


# ---------------------------------------------------------------------------
# NODE 6 — clarification_node
# ---------------------------------------------------------------------------


def clarification_node(state: AgentState) -> dict:
    question = (
        state.get("clarification_question")
        or "Could you provide more details about your request?"
    )
    prompt = build_clarification_prompt(question, state.get("customer_name"))
    text = _call_llm_for_text(prompt, SYSTEM_PROMPT)
    return {
        "final_response": text if text else question,
        "current_node": "clarification",
    }


# ---------------------------------------------------------------------------
# NODE 7 — deflection_node
# ---------------------------------------------------------------------------


def deflection_node(state: AgentState) -> dict:
    prompt = build_deflection_prompt(state.get("customer_name"))
    text = _call_llm_for_text(prompt, SYSTEM_PROMPT)
    return {
        "final_response": text if text else _DEFLECTION_FALLBACK,
        "current_node": "deflection",
    }


# ---------------------------------------------------------------------------
# NODE 8 — logging_node
# ---------------------------------------------------------------------------


def logging_node(state: AgentState, db: Session) -> dict:
    start_time = state.get("start_time")
    latency_ms: int | None = (
        int((time.time() - start_time) * 1000) if start_time else None
    )
    try:
        log = AgentLog(
            conversation_id=state["conversation_id"],
            refund_request_id=state.get("refund_request_id"),
            user_message=state["user_message"],
            parsed_intent=state.get("parsed_intent"),
            tool_calls=state.get("tool_calls_log"),
            policy_input=state.get("refund_context"),
            policy_decision=state.get("policy_decision"),
            final_response=state.get("final_response"),
            injection_flags=state.get("injection_flags"),
            latency_ms=latency_ms,
        )
        db.add(log)
        db.commit()
    except Exception as exc:
        logger.error("Failed to write AgentLog: %s", exc, exc_info=True)
        try:
            db.rollback()
        except Exception:
            pass
    return {"current_node": "logging"}


__all__ = [
    "AgentState",
    "safety_check_node",
    "intent_extraction_node",
    "identity_resolution_node",
    "context_assembly_node",
    "policy_evaluation_node",
    "response_composition_node",
    "clarification_node",
    "deflection_node",
    "logging_node",
]
