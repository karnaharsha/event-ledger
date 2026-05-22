from datetime import datetime, timezone
from sqlalchemy import Column, String, Numeric, DateTime, JSON, UniqueConstraint
from .database import Base


class Event(Base):
    __tablename__ = "events"

    event_id = Column(String, primary_key=True, index=True)
    account_id = Column(String, nullable=False, index=True)
    type = Column(String, nullable=False)
    amount = Column(Numeric(precision=18, scale=6), nullable=False)
    currency = Column(String, nullable=False)
    event_timestamp = Column(DateTime(timezone=True), nullable=False)
    metadata_ = Column("metadata", JSON, nullable=True)
    received_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
