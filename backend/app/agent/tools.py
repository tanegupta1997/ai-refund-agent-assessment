from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Generic, TypeVar

from sqlalchemy.orm import Session

from app.db.models import Customer, Order, OrderItem, Product, RefundRequest
from app.policy.engine import RefundContext

T = TypeVar("T")


# ---------------------------------------------------------------------------
# Tool result wrapper
# ---------------------------------------------------------------------------


@dataclass
class ToolResult(Generic[T]):
    success: bool
    data: T | None
    error: str | None
    tool_name: str


def ok(tool_name: str, data: T) -> ToolResult[T]:
    return ToolResult(success=True, data=data, error=None, tool_name=tool_name)


def err(tool_name: str, error: str) -> ToolResult[Any]:
    return ToolResult(success=False, data=None, error=error, tool_name=tool_name)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _dt(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


# ---------------------------------------------------------------------------
# Tool 1 — lookup_customer
# ---------------------------------------------------------------------------


def lookup_customer(db: Session, identifier: str) -> ToolResult[dict]:
    customer = db.query(Customer).filter(Customer.email == identifier).first()
    if customer is None:
        customer = db.query(Customer).filter(Customer.customer_id == identifier).first()
    if customer is None:
        return err("lookup_customer", f"No customer found for identifier: {identifier}")
    return ok("lookup_customer", {
        "customer_id": customer.customer_id,
        "name": customer.name,
        "email": customer.email,
        "phone": customer.phone,
        "loyalty_tier": customer.loyalty_tier,
        "created_at": _dt(customer.created_at),
    })


# ---------------------------------------------------------------------------
# Tool 2 — get_orders_for_customer
# ---------------------------------------------------------------------------


def get_orders_for_customer(db: Session, customer_id: str) -> ToolResult[list[dict]]:
    customer = db.query(Customer).filter(Customer.customer_id == customer_id).first()
    if customer is None:
        return err("get_orders_for_customer", f"No customer found with id: {customer_id}")
    orders = (
        db.query(Order)
        .filter(Order.customer_id == customer_id)
        .order_by(Order.order_date.desc())
        .all()
    )
    result = []
    for order in orders:
        item_count = db.query(OrderItem).filter(OrderItem.order_id == order.order_id).count()
        result.append({
            "order_id": order.order_id,
            "order_date": _dt(order.order_date),
            "delivery_date": _dt(order.delivery_date),
            "status": order.status,
            "total_amount": order.total_amount,
            "currency": order.currency,
            "item_count": item_count,
        })
    return ok("get_orders_for_customer", result)


# ---------------------------------------------------------------------------
# Tool 3 — get_order_detail
# ---------------------------------------------------------------------------


def get_order_detail(db: Session, order_id: str, customer_id: str) -> ToolResult[dict]:
    order = db.query(Order).filter(Order.order_id == order_id).first()
    if order is None:
        return err("get_order_detail", f"No order found with id: {order_id}")
    if order.customer_id != customer_id:
        return err("get_order_detail", "Order does not belong to this customer")
    items = db.query(OrderItem).filter(OrderItem.order_id == order_id).all()
    item_dicts = []
    for item in items:
        product = db.query(Product).filter(Product.product_id == item.product_id).first()
        item_dicts.append({
            "order_item_id": item.order_item_id,
            "product_id": item.product_id,
            "product_name": product.name if product else None,
            "category": product.category if product else None,
            "unit_price": product.unit_price if product else None,
            "quantity": item.quantity,
            "line_total": item.line_total,
            "condition_on_arrival": item.condition_on_arrival,
            "is_final_sale": product.is_final_sale if product else None,
            "is_refundable_default": product.is_refundable_default if product else None,
        })
    return ok("get_order_detail", {
        "order_id": order.order_id,
        "customer_id": order.customer_id,
        "order_date": _dt(order.order_date),
        "delivery_date": _dt(order.delivery_date),
        "status": order.status,
        "total_amount": order.total_amount,
        "currency": order.currency,
        "items": item_dicts,
    })


# ---------------------------------------------------------------------------
# Tool 4 — get_product_metadata
# ---------------------------------------------------------------------------


def get_product_metadata(db: Session, product_id: str) -> ToolResult[dict]:
    product = db.query(Product).filter(Product.product_id == product_id).first()
    if product is None:
        return err("get_product_metadata", f"No product found with id: {product_id}")
    return ok("get_product_metadata", {
        "product_id": product.product_id,
        "name": product.name,
        "category": product.category,
        "unit_price": product.unit_price,
        "is_final_sale": product.is_final_sale,
        "is_refundable_default": product.is_refundable_default,
    })


# ---------------------------------------------------------------------------
# Tool 5 — build_refund_context
# ---------------------------------------------------------------------------


def build_refund_context(
    db: Session,
    customer_id: str,
    order_id: str,
    order_item_id: str,
    requested_amount: float,
    reason_category: str,
    evidence_provided: bool,
    evidence_note: str | None,
    evaluated_at: datetime,
) -> ToolResult[RefundContext]:
    customer = db.query(Customer).filter(Customer.customer_id == customer_id).first()
    if customer is None:
        return err("build_refund_context", f"No customer found with id: {customer_id}")

    order = db.query(Order).filter(Order.order_id == order_id).first()
    if order is None:
        return err("build_refund_context", f"No order found with id: {order_id}")
    if order.customer_id != customer_id:
        return err("build_refund_context", "Order does not belong to this customer")

    item = db.query(OrderItem).filter(OrderItem.order_item_id == order_item_id).first()
    if item is None:
        return err("build_refund_context", f"No order item found with id: {order_item_id}")
    if item.order_id != order_id:
        return err("build_refund_context", "Order item does not belong to this order")

    product = db.query(Product).filter(Product.product_id == item.product_id).first()
    if product is None:
        return err("build_refund_context", f"No product found with id: {item.product_id}")

    ctx = RefundContext(
        customer_id=customer.customer_id,
        customer_loyalty_tier=customer.loyalty_tier,
        order_id=order.order_id,
        order_status=order.status,
        order_date=order.order_date,
        delivery_date=order.delivery_date,
        order_total=order.total_amount,
        order_item_id=item.order_item_id,
        product_id=product.product_id,
        product_name=product.name,
        is_final_sale=product.is_final_sale,
        is_refundable_default=product.is_refundable_default,
        condition_on_arrival=item.condition_on_arrival,
        requested_amount=requested_amount,
        reason_category=reason_category,
        evidence_provided=evidence_provided,
        evidence_note=evidence_note,
        evaluated_at=evaluated_at,
    )
    return ok("build_refund_context", ctx)


# ---------------------------------------------------------------------------
# Tool 6 — get_refund_request_status
# ---------------------------------------------------------------------------


def get_refund_request_status(
    db: Session,
    refund_request_id: str,
    customer_id: str,
) -> ToolResult[dict]:
    req = db.query(RefundRequest).filter(
        RefundRequest.refund_request_id == refund_request_id
    ).first()
    if req is None:
        return err("get_refund_request_status", f"No refund request found with id: {refund_request_id}")
    if req.customer_id != customer_id:
        return err("get_refund_request_status", "Refund request does not belong to this customer")
    return ok("get_refund_request_status", {
        "refund_request_id": req.refund_request_id,
        "order_id": req.order_id,
        "requested_amount": req.requested_amount,
        "reason_category": req.reason_category,
        "decision": req.decision,
        "decision_reasons": req.decision_reasons,
        "created_at": _dt(req.created_at),
        "decided_at": _dt(req.decided_at),
    })


# ---------------------------------------------------------------------------
# Tool registry
# ---------------------------------------------------------------------------


TOOL_REGISTRY: dict[str, Callable] = {
    "lookup_customer": lookup_customer,
    "get_orders_for_customer": get_orders_for_customer,
    "get_order_detail": get_order_detail,
    "get_product_metadata": get_product_metadata,
    "build_refund_context": build_refund_context,
    "get_refund_request_status": get_refund_request_status,
}


def get_tool_definitions() -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": "lookup_customer",
                "description": "Look up a customer by email address or customer_id. Try email first.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "identifier": {
                            "type": "string",
                            "description": "Customer email address or customer_id",
                        },
                    },
                    "required": ["identifier"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_orders_for_customer",
                "description": "Return all orders for a customer, ordered newest first. Returns an empty list if the customer has no orders.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "customer_id": {
                            "type": "string",
                            "description": "The customer's customer_id",
                        },
                    },
                    "required": ["customer_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_order_detail",
                "description": "Return full detail for a single order including all line items. Verifies the order belongs to the given customer.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "order_id": {
                            "type": "string",
                            "description": "The order's order_id",
                        },
                        "customer_id": {
                            "type": "string",
                            "description": "Must match the order's customer_id",
                        },
                    },
                    "required": ["order_id", "customer_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_product_metadata",
                "description": "Return refund-relevant metadata for a product: whether it is final sale, whether it is refundable by default, price, and category.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "product_id": {
                            "type": "string",
                            "description": "The product's product_id",
                        },
                    },
                    "required": ["product_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "build_refund_context",
                "description": "Assemble a RefundContext from all required DB facts. Call this immediately before evaluating the refund policy. Returns a RefundContext ready for engine.evaluate().",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "customer_id": {"type": "string", "description": "Customer's customer_id"},
                        "order_id": {"type": "string", "description": "Order's order_id"},
                        "order_item_id": {"type": "string", "description": "The specific order_item_id being refunded"},
                        "requested_amount": {"type": "number", "description": "Amount the customer is requesting to be refunded"},
                        "reason_category": {
                            "type": "string",
                            "enum": ["changed_mind", "damaged", "defective", "never_arrived", "wrong_item", "other"],
                            "description": "Category of the refund reason",
                        },
                        "evidence_provided": {"type": "boolean", "description": "Whether the customer has provided evidence (photo, etc.)"},
                        "evidence_note": {"type": "string", "description": "Optional description of the evidence provided", "nullable": True},
                        "evaluated_at": {"type": "string", "format": "date-time", "description": "ISO 8601 timestamp at which the policy is being evaluated"},
                    },
                    "required": [
                        "customer_id", "order_id", "order_item_id",
                        "requested_amount", "reason_category",
                        "evidence_provided", "evaluated_at",
                    ],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_refund_request_status",
                "description": "Look up the status of a previously submitted refund request. Verifies the request belongs to the given customer.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "refund_request_id": {
                            "type": "string",
                            "description": "The refund request's refund_request_id",
                        },
                        "customer_id": {
                            "type": "string",
                            "description": "Must match the refund request's customer_id",
                        },
                    },
                    "required": ["refund_request_id", "customer_id"],
                },
            },
        },
    ]


__all__ = [
    "ToolResult",
    "lookup_customer",
    "get_orders_for_customer",
    "get_order_detail",
    "get_product_metadata",
    "build_refund_context",
    "get_refund_request_status",
    "TOOL_REGISTRY",
    "get_tool_definitions",
]
