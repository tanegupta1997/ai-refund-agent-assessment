from __future__ import annotations

import logging
import time
from functools import partial

from langgraph.graph import END, StateGraph
from sqlalchemy.orm import Session

from app.agent.nodes import (
    AgentState,
    clarification_node,
    context_assembly_node,
    deflection_node,
    identity_resolution_node,
    intent_extraction_node,
    logging_node,
    policy_evaluation_node,
    response_composition_node,
    safety_check_node,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Routing functions
# ---------------------------------------------------------------------------


def route_after_safety(state: AgentState) -> str:
    if state.get("injection_detected"):
        return "deflection"
    return "intent_extraction"


def route_after_intent(state: AgentState) -> str:
    if state.get("error_message"):
        return "clarification"
    if not state.get("is_refund_request"):
        return "clarification"
    if state.get("needs_clarification"):
        return "clarification"
    return "identity_resolution"


def route_after_identity(state: AgentState) -> str:
    if state.get("error_message"):
        return "clarification"
    if state.get("needs_clarification"):
        return "clarification"
    return "context_assembly"


def route_after_context(state: AgentState) -> str:
    if state.get("error_message"):
        return "clarification"
    if state.get("needs_clarification"):
        return "clarification"
    return "policy_evaluation"


# ---------------------------------------------------------------------------
# Graph compilation
# ---------------------------------------------------------------------------


def compile_graph(db: Session):
    """
    Builds and compiles the LangGraph state machine.
    Called once per request with a fresh db session.
    """
    workflow: StateGraph = StateGraph(AgentState)

    # Register nodes — db-dependent ones have session bound via partial
    workflow.add_node("safety_check", safety_check_node)
    workflow.add_node("intent_extraction", intent_extraction_node)
    workflow.add_node("identity_resolution", partial(identity_resolution_node, db=db))
    workflow.add_node("context_assembly", partial(context_assembly_node, db=db))
    workflow.add_node("policy_evaluation", policy_evaluation_node)
    workflow.add_node("response_composition", partial(response_composition_node, db=db))
    workflow.add_node("clarification", clarification_node)
    workflow.add_node("deflection", deflection_node)
    workflow.add_node("logging", partial(logging_node, db=db))

    # Entry point
    workflow.set_entry_point("safety_check")

    # Conditional edges
    workflow.add_conditional_edges(
        "safety_check",
        route_after_safety,
        {"deflection": "deflection", "intent_extraction": "intent_extraction"},
    )
    workflow.add_conditional_edges(
        "intent_extraction",
        route_after_intent,
        {"clarification": "clarification", "identity_resolution": "identity_resolution"},
    )
    workflow.add_conditional_edges(
        "identity_resolution",
        route_after_identity,
        {"clarification": "clarification", "context_assembly": "context_assembly"},
    )
    workflow.add_conditional_edges(
        "context_assembly",
        route_after_context,
        {"clarification": "clarification", "policy_evaluation": "policy_evaluation"},
    )

    # Fixed edges
    workflow.add_edge("policy_evaluation", "response_composition")
    workflow.add_edge("response_composition", "logging")
    workflow.add_edge("clarification", "logging")
    workflow.add_edge("deflection", "logging")
    workflow.add_edge("logging", END)

    return workflow.compile()


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run_agent(
    conversation_id: str,
    user_message: str,
    conversation_history: list[dict],
    db: Session,
) -> dict:
    """
    Single public function called by the FastAPI route.
    Builds initial state, compiles graph, invokes it,
    and returns a clean response dict.
    """
    initial_state: AgentState = {
        "conversation_id": conversation_id,
        "user_message": user_message,
        "conversation_history": conversation_history,
        "start_time": time.time(),
        # Identity
        "customer_id": None,
        "customer_name": None,
        "customer_data": None,
        # Order
        "order_id": None,
        "order_data": None,
        "order_item_id": None,
        # Intent
        "parsed_intent": None,
        "needs_clarification": False,
        "clarification_question": None,
        "is_refund_request": False,
        # Refund details
        "requested_amount": None,
        "reason_category": None,
        "evidence_provided": False,
        "evidence_note": None,
        # Policy
        "refund_context": None,
        "policy_decision": None,
        "verdict": None,
        # Safety
        "injection_detected": False,
        "injection_flags": [],
        # Logs
        "tool_calls_log": [],
        # Output
        "final_response": None,
        "refund_request_id": None,
        "error_message": None,
        "current_node": "start",
    }

    graph = compile_graph(db)

    try:
        final_state = graph.invoke(initial_state)
    except Exception as exc:
        logger.critical("Graph invocation failed: %s", exc, exc_info=True)
        return {
            "conversation_id": conversation_id,
            "reply": (
                "We encountered an unexpected error. "
                "Your request has been logged and a human will follow up shortly."
            ),
            "verdict": "escalated",
            "refund_request_id": None,
            "needs_clarification": False,
            "injection_detected": False,
            "current_node": "error",
        }

    return {
        "conversation_id": conversation_id,
        "reply": (
            final_state.get("final_response")
            or "I'm sorry, something went wrong. Please try again."
        ),
        "verdict": final_state.get("verdict"),
        "refund_request_id": final_state.get("refund_request_id"),
        "needs_clarification": final_state.get("needs_clarification", False),
        "injection_detected": final_state.get("injection_detected", False),
        "current_node": final_state.get("current_node"),
    }


__all__ = ["run_agent", "compile_graph"]
