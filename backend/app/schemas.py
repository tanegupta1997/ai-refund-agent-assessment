from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class OrderStatus(str, Enum):
    delivered = "delivered"
    in_transit = "in_transit"
    cancelled = "cancelled"


class ConditionOnArrival(str, Enum):
    ok = "ok"
    damaged = "damaged"
    defective = "defective"
    unknown = "unknown"


class ReasonCategory(str, Enum):
    changed_mind = "changed_mind"
    damaged = "damaged"
    defective = "defective"
    never_arrived = "never_arrived"
    wrong_item = "wrong_item"
    other = "other"


class Decision(str, Enum):
    approved = "approved"
    denied = "denied"
    escalated = "escalated"
    pending = "pending"


# ---------------------------------------------------------------------------
# Customer
# ---------------------------------------------------------------------------


class CustomerBase(BaseModel):
    name: str
    email: str
    phone: str | None = None
    loyalty_tier: str | None = None


class CustomerCreate(CustomerBase):
    pass


class Customer(CustomerBase):
    model_config = ConfigDict(from_attributes=True)

    customer_id: int
    created_at: datetime


# ---------------------------------------------------------------------------
# Product
# ---------------------------------------------------------------------------


class ProductBase(BaseModel):
    name: str
    category: str | None = None
    unit_price: float
    is_final_sale: bool
    is_refundable_default: bool


class ProductCreate(ProductBase):
    pass


class Product(ProductBase):
    model_config = ConfigDict(from_attributes=True)

    product_id: int


# ---------------------------------------------------------------------------
# Order
# ---------------------------------------------------------------------------


class OrderBase(BaseModel):
    customer_id: int
    order_date: datetime
    delivery_date: datetime | None = None
    status: OrderStatus
    total_amount: float
    currency: str


class OrderCreate(OrderBase):
    pass


class Order(OrderBase):
    model_config = ConfigDict(from_attributes=True)

    order_id: int


# ---------------------------------------------------------------------------
# Order Item
# ---------------------------------------------------------------------------


class OrderItemBase(BaseModel):
    order_id: int
    product_id: int
    quantity: int
    line_total: float
    condition_on_arrival: ConditionOnArrival


class OrderItemCreate(OrderItemBase):
    pass


class OrderItem(OrderItemBase):
    model_config = ConfigDict(from_attributes=True)

    order_item_id: int


# ---------------------------------------------------------------------------
# Refund Request
# ---------------------------------------------------------------------------


class RefundRequestBase(BaseModel):
    customer_id: int
    order_id: int
    order_item_id: int | None = None
    requested_amount: float
    reason_category: ReasonCategory
    evidence_provided: bool
    evidence_note: str | None = None
    decision: Decision = Decision.pending
    decision_reasons: list[Any] = []


class RefundRequestCreate(RefundRequestBase):
    pass


class RefundRequest(RefundRequestBase):
    model_config = ConfigDict(from_attributes=True)

    refund_request_id: int
    created_at: datetime
    decided_at: datetime | None = None


# ---------------------------------------------------------------------------
# Agent Log
# ---------------------------------------------------------------------------


class ToolCallRecord(BaseModel):
    tool: str
    args: dict[str, Any]
    result_summary: str | None = None


class AgentLogBase(BaseModel):
    conversation_id: str
    refund_request_id: int | None = None
    timestamp: datetime
    user_message: str
    parsed_intent: dict[str, Any] | None = None
    tool_calls: list[ToolCallRecord] = []
    policy_input: dict[str, Any] | None = None
    policy_decision: dict[str, Any] | None = None
    final_response: str
    injection_flags: dict[str, Any] | None = None
    latency_ms: int | None = None


class AgentLogCreate(AgentLogBase):
    pass


class AgentLog(AgentLogBase):
    model_config = ConfigDict(from_attributes=True)

    log_id: int
