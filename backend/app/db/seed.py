from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

from app.db.models import Customer, Order, OrderItem, Product
from app.db.session import SessionLocal

logger = logging.getLogger(__name__)

_FIXTURES = Path(__file__).parent.parent.parent / "fixtures"

_DATETIME_FIELDS = {
    "Customer": ("created_at",),
    "Order": ("order_date", "delivery_date"),
}


def _load(filename: str) -> list[dict]:
    with open(_FIXTURES / filename) as f:
        return json.load(f)


def _parse_datetimes(model_name: str, row: dict) -> dict:
    for field in _DATETIME_FIELDS.get(model_name, ()):
        if row.get(field) is not None:
            row[field] = datetime.fromisoformat(row[field])
    return row


def run_seed() -> None:
    db = SessionLocal()
    try:
        _seed_products(db)
        _seed_customers(db)
        _seed_orders(db)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _seed_products(db) -> None:
    if db.query(Product).first():
        logger.info("already seeded: products")
        return
    rows = _load("products.json")
    for r in rows:
        db.add(Product(**r))
    logger.info("seeded %d products", len(rows))


def _seed_customers(db) -> None:
    if db.query(Customer).first():
        logger.info("already seeded: customers")
        return
    rows = _load("customers.json")
    for r in rows:
        db.add(Customer(**_parse_datetimes("Customer", r)))
    logger.info("seeded %d customers", len(rows))


def _seed_orders(db) -> None:
    if db.query(Order).first():
        logger.info("already seeded: orders")
        return
    order_rows = _load("orders.json")
    order_count = 0
    item_count = 0
    for r in order_rows:
        items = r.pop("items")
        db.add(Order(**_parse_datetimes("Order", r)))
        order_count += 1
        for item in items:
            db.add(OrderItem(order_id=r["order_id"], **item))
            item_count += 1
    logger.info("seeded %d orders", order_count)
    logger.info("seeded %d order_items", item_count)
