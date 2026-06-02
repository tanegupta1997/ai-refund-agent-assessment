from __future__ import annotations

import os
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Base

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./refund_agent.db")

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    Base.metadata.create_all(bind=engine)


__all__ = ["engine", "SessionLocal", "get_db", "init_db"]
