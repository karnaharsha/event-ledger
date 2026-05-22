from datetime import datetime
from decimal import Decimal
from typing import Any, Literal, Optional
from pydantic import BaseModel, Field, field_validator


class EventCreate(BaseModel):
    eventId: str = Field(..., min_length=1)
    accountId: str = Field(..., min_length=1)
    type: Literal["CREDIT", "DEBIT"]
    amount: Decimal = Field(..., gt=0, description="Must be greater than 0")
    currency: str = Field(..., min_length=1)
    eventTimestamp: datetime
    metadata: Optional[dict[str, Any]] = None


class EventResponse(BaseModel):
    eventId: str
    accountId: str
    type: str
    amount: Decimal
    currency: str
    eventTimestamp: datetime
    metadata: Optional[dict[str, Any]] = None
    receivedAt: datetime

    model_config = {"from_attributes": True}


class BalanceResponse(BaseModel):
    accountId: str
    balance: Decimal
    currency: str
