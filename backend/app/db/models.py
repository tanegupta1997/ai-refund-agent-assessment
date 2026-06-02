from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Customer
# ---------------------------------------------------------------------------


class Customer(Base):
    __tablename__ = "customers"

    customer_id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String, nullable=False)
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    phone: Mapped[str | None] = mapped_column(String, nullable=True)
    loyalty_tier: Mapped[str] = mapped_column(String, nullable=False, default="standard")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)

    orders: Mapped[list["Order"]] = relationship("Order", back_populates="customer")

    def __repr__(self) -> str:
        return f"<Customer customer_id={self.customer_id!r} name={self.name!r}>"


# ---------------------------------------------------------------------------
# Product
# ---------------------------------------------------------------------------


class Product(Base):
    __tablename__ = "products"

    product_id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String, nullable=False)
    category: Mapped[str] = mapped_column(String, nullable=False)
    unit_price: Mapped[float] = mapped_column(Float, nullable=False)
    is_final_sale: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_refundable_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    def __repr__(self) -> str:
        return f"<Product product_id={self.product_id!r} name={self.name!r}>"


# ---------------------------------------------------------------------------
# Order
# ---------------------------------------------------------------------------


class Order(Base):
    __tablename__ = "orders"

    order_id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    customer_id: Mapped[str] = mapped_column(String, ForeignKey("customers.customer_id"), nullable=False)
    order_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    delivery_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False)
    total_amount: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String, nullable=False, default="USD")

    customer: Mapped["Customer"] = relationship("Customer", back_populates="orders")
    items: Mapped[list["OrderItem"]] = relationship("OrderItem", back_populates="order")

    def __repr__(self) -> str:
        return f"<Order order_id={self.order_id!r} status={self.status!r}>"


# ---------------------------------------------------------------------------
# OrderItem
# ---------------------------------------------------------------------------


class OrderItem(Base):
    __tablename__ = "order_items"

    order_item_id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    order_id: Mapped[str] = mapped_column(String, ForeignKey("orders.order_id"), nullable=False)
    product_id: Mapped[str] = mapped_column(String, ForeignKey("products.product_id"), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    line_total: Mapped[float] = mapped_column(Float, nullable=False)
    condition_on_arrival: Mapped[str] = mapped_column(String, nullable=False, default="ok")

    order: Mapped["Order"] = relationship("Order", back_populates="items")
    product: Mapped["Product"] = relationship("Product")

    def __repr__(self) -> str:
        return f"<OrderItem order_item_id={self.order_item_id!r} product_id={self.product_id!r}>"


# ---------------------------------------------------------------------------
# RefundRequest
# ---------------------------------------------------------------------------


class RefundRequest(Base):
    __tablename__ = "refund_requests"

    refund_request_id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    customer_id: Mapped[str] = mapped_column(String, ForeignKey("customers.customer_id"), nullable=False)
    order_id: Mapped[str] = mapped_column(String, ForeignKey("orders.order_id"), nullable=False)
    order_item_id: Mapped[str | None] = mapped_column(String, ForeignKey("order_items.order_item_id"), nullable=True)
    requested_amount: Mapped[float] = mapped_column(Float, nullable=False)
    reason_category: Mapped[str] = mapped_column(String, nullable=False)
    evidence_provided: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    evidence_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    decision: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    decision_reasons: Mapped[list | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    customer: Mapped["Customer"] = relationship("Customer")
    order: Mapped["Order"] = relationship("Order")
    order_item: Mapped["OrderItem | None"] = relationship("OrderItem")

    def __repr__(self) -> str:
        return f"<RefundRequest refund_request_id={self.refund_request_id!r} decision={self.decision!r}>"


# ---------------------------------------------------------------------------
# AgentLog
# ---------------------------------------------------------------------------


class AgentLog(Base):
    __tablename__ = "agent_logs"

    log_id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    conversation_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    refund_request_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("refund_requests.refund_request_id"), nullable=True
    )
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    user_message: Mapped[str] = mapped_column(Text, nullable=False)
    parsed_intent: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    tool_calls: Mapped[list | None] = mapped_column(JSON, nullable=True)
    policy_input: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    policy_decision: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    final_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    injection_flags: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    refund_request: Mapped["RefundRequest | None"] = relationship("RefundRequest")

    def __repr__(self) -> str:
        return f"<AgentLog log_id={self.log_id!r} conversation_id={self.conversation_id!r}>"


__all__ = ["Base", "Customer", "Product", "Order", "OrderItem", "RefundRequest", "AgentLog"]
