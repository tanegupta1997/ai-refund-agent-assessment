from __future__ import annotations

import hmac
import logging
from uuid import uuid4

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.agent.graph import run_agent
from app.config import settings
from app.db.models import AgentLog, Customer, Order, RefundRequest
from app.db.seed import run_seed
from app.db.session import get_db, init_db

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    run_seed()
    logger.info("Application started. DB ready.")
    yield


app = FastAPI(
    title="AI Refund Agent API",
    version="1.0.0",
    description="AI-powered customer refund processing",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.ALLOWED_ORIGINS.split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------


class ChatRequest(BaseModel):
    conversation_id: str = Field(default_factory=lambda: str(uuid4()))
    message: str = Field(min_length=1, max_length=2000)
    conversation_history: list[dict] = Field(default_factory=list)


class ChatResponse(BaseModel):
    conversation_id: str
    reply: str
    verdict: str | None
    refund_request_id: str | None
    needs_clarification: bool
    injection_detected: bool


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _serialize_dt(dt) -> str | None:
    return dt.isoformat() if dt else None


def _paginate(query, page: int, page_size: int):
    total = query.count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()
    return total, items


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------


def verify_admin(x_admin_secret: str | None = Header(None)) -> None:
    provided = x_admin_secret or ""
    if not hmac.compare_digest(provided, settings.ADMIN_SECRET):
        raise HTTPException(status_code=401, detail="Invalid admin secret")


# ---------------------------------------------------------------------------
# Global exception handler
# ---------------------------------------------------------------------------


@app.exception_handler(Exception)
async def global_exception_handler(request, exc: Exception):
    logger.critical("Unhandled error: %s", exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal error occurred. Please try again."},
    )


# ---------------------------------------------------------------------------
# ENDPOINT 1 — Health check
# ---------------------------------------------------------------------------


@app.get("/health")
async def health():
    return {"status": "ok", "model": settings.MODEL_NAME}


# ---------------------------------------------------------------------------
# ENDPOINT 2 — Chat
# ---------------------------------------------------------------------------


@app.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    db: Session = Depends(get_db),
):
    if not request.message.strip():
        raise HTTPException(status_code=422, detail="Message cannot be empty.")

    try:
        result = run_agent(
            conversation_id=request.conversation_id,
            user_message=request.message,
            conversation_history=request.conversation_history,
            db=db,
        )
        return ChatResponse(
            conversation_id=result["conversation_id"],
            reply=result.get("reply") or "I'm sorry, something went wrong. Please try again.",
            verdict=result.get("verdict"),
            refund_request_id=result.get("refund_request_id"),
            needs_clarification=result.get("needs_clarification", False),
            injection_detected=result.get("injection_detected", False),
        )
    except Exception as exc:
        logger.error("Chat endpoint error (conversation_id=%s): %s", request.conversation_id, exc, exc_info=True)
        return ChatResponse(
            conversation_id=request.conversation_id,
            reply="We encountered an unexpected error. Please try again or contact support.",
            verdict=None,
            refund_request_id=None,
            needs_clarification=False,
            injection_detected=False,
        )


# ---------------------------------------------------------------------------
# ENDPOINT 3 — Admin: list logs
# ---------------------------------------------------------------------------


@app.get("/admin/logs")
def list_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    conversation_id: str | None = Query(None),
    db: Session = Depends(get_db),
    _: None = Depends(verify_admin),
):
    query = db.query(AgentLog)
    if conversation_id:
        query = query.filter(AgentLog.conversation_id == conversation_id).order_by(AgentLog.timestamp.asc())
    else:
        query = query.order_by(AgentLog.timestamp.desc())

    total, rows = _paginate(query, page, page_size)

    items = []
    for row in rows:
        pd = row.policy_decision or {}
        flags = row.injection_flags or []
        items.append({
            "log_id": row.log_id,
            "conversation_id": row.conversation_id,
            "timestamp": _serialize_dt(row.timestamp),
            "user_message": (row.user_message or "")[:100],
            "current_node": pd.get("current_node", "unknown") if isinstance(pd, dict) else "unknown",
            "verdict": pd.get("verdict") if isinstance(pd, dict) else None,
            "injection_detected": isinstance(flags, list) and len(flags) > 0,
            "latency_ms": row.latency_ms,
            "refund_request_id": row.refund_request_id,
        })

    return {"total": total, "page": page, "page_size": page_size, "items": items}


# ---------------------------------------------------------------------------
# ENDPOINT 4 — Admin: log detail
# ---------------------------------------------------------------------------


@app.get("/admin/logs/{log_id}")
def get_log(
    log_id: str,
    db: Session = Depends(get_db),
    _: None = Depends(verify_admin),
):
    row = db.query(AgentLog).filter(AgentLog.log_id == log_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Log not found.")
    return {
        "log_id": row.log_id,
        "conversation_id": row.conversation_id,
        "timestamp": _serialize_dt(row.timestamp),
        "user_message": row.user_message,
        "parsed_intent": row.parsed_intent,
        "tool_calls": row.tool_calls,
        "policy_input": row.policy_input,
        "policy_decision": row.policy_decision,
        "final_response": row.final_response,
        "injection_flags": row.injection_flags,
        "latency_ms": row.latency_ms,
        "refund_request_id": row.refund_request_id,
    }


# ---------------------------------------------------------------------------
# ENDPOINT 5 — Admin: list refund requests
# ---------------------------------------------------------------------------


@app.get("/admin/refund-requests")
def list_refund_requests(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    decision: str | None = Query(None),
    customer_id: str | None = Query(None),
    db: Session = Depends(get_db),
    _: None = Depends(verify_admin),
):
    query = db.query(RefundRequest).order_by(RefundRequest.created_at.desc())
    if decision:
        query = query.filter(RefundRequest.decision == decision)
    if customer_id:
        query = query.filter(RefundRequest.customer_id == customer_id)

    total, rows = _paginate(query, page, page_size)

    items = [
        {
            "refund_request_id": r.refund_request_id,
            "customer_id": r.customer_id,
            "order_id": r.order_id,
            "order_item_id": r.order_item_id,
            "requested_amount": r.requested_amount,
            "reason_category": r.reason_category,
            "evidence_provided": r.evidence_provided,
            "decision": r.decision,
            "decision_reasons": r.decision_reasons,
            "created_at": _serialize_dt(r.created_at),
            "decided_at": _serialize_dt(r.decided_at),
        }
        for r in rows
    ]
    return {"total": total, "page": page, "page_size": page_size, "items": items}


# ---------------------------------------------------------------------------
# ENDPOINT 6 — Admin: refund request detail
# ---------------------------------------------------------------------------


@app.get("/admin/refund-requests/{refund_request_id}")
def get_refund_request(
    refund_request_id: str,
    db: Session = Depends(get_db),
    _: None = Depends(verify_admin),
):
    r = db.query(RefundRequest).filter(
        RefundRequest.refund_request_id == refund_request_id
    ).first()
    if not r:
        raise HTTPException(status_code=404, detail="Refund request not found.")

    customer = db.query(Customer).filter(Customer.customer_id == r.customer_id).first()
    order = db.query(Order).filter(Order.order_id == r.order_id).first()

    return {
        "refund_request_id": r.refund_request_id,
        "customer_id": r.customer_id,
        "customer_name": customer.name if customer else None,
        "order_id": r.order_id,
        "order_total": order.total_amount if order else None,
        "order_item_id": r.order_item_id,
        "requested_amount": r.requested_amount,
        "reason_category": r.reason_category,
        "evidence_provided": r.evidence_provided,
        "evidence_note": r.evidence_note,
        "decision": r.decision,
        "decision_reasons": r.decision_reasons,
        "created_at": _serialize_dt(r.created_at),
        "decided_at": _serialize_dt(r.decided_at),
    }


# ---------------------------------------------------------------------------
# ENDPOINT 7 — Admin: list customers
# ---------------------------------------------------------------------------


@app.get("/admin/customers")
def list_customers(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _: None = Depends(verify_admin),
):
    query = db.query(Customer).order_by(Customer.created_at.desc())
    total, rows = _paginate(query, page, page_size)

    items = []
    for c in rows:
        order_count = db.query(Order).filter(Order.customer_id == c.customer_id).count()
        items.append({
            "customer_id": c.customer_id,
            "name": c.name,
            "email": c.email,
            "phone": c.phone,
            "loyalty_tier": c.loyalty_tier,
            "created_at": _serialize_dt(c.created_at),
            "order_count": order_count,
        })

    return {"total": total, "page": page, "page_size": page_size, "items": items}


# ---------------------------------------------------------------------------
# ENDPOINT 8 — Admin: escalation queue
# ---------------------------------------------------------------------------


@app.get("/admin/escalations")
def list_escalations(
    db: Session = Depends(get_db),
    _: None = Depends(verify_admin),
):
    rows = (
        db.query(RefundRequest)
        .filter(RefundRequest.decision == "escalated")
        .order_by(RefundRequest.created_at.desc())
        .all()
    )
    items = [
        {
            "refund_request_id": r.refund_request_id,
            "customer_id": r.customer_id,
            "order_id": r.order_id,
            "order_item_id": r.order_item_id,
            "requested_amount": r.requested_amount,
            "reason_category": r.reason_category,
            "evidence_provided": r.evidence_provided,
            "decision": r.decision,
            "decision_reasons": r.decision_reasons,
            "created_at": _serialize_dt(r.created_at),
            "decided_at": _serialize_dt(r.decided_at),
        }
        for r in rows
    ]
    return {"count": len(items), "items": items}
