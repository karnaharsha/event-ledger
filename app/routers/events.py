from datetime import timezone
from decimal import Decimal
from typing import Optional

import math

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Event
from ..schemas import EventCreate, EventResponse, PaginatedEventsResponse

router = APIRouter(prefix="/events", tags=["events"])


def _to_response(event: Event) -> EventResponse:
    ts = event.event_timestamp
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    received = event.received_at
    if received.tzinfo is None:
        received = received.replace(tzinfo=timezone.utc)
    return EventResponse(
        eventId=event.event_id,
        accountId=event.account_id,
        type=event.type,
        amount=Decimal(str(event.amount)),
        currency=event.currency,
        eventTimestamp=ts,
        metadata=event.metadata_,
        receivedAt=received,
    )


@router.post("", status_code=status.HTTP_201_CREATED, response_model=EventResponse)
def submit_event(payload: EventCreate, response: Response, db: Session = Depends(get_db)):
    existing = db.get(Event, payload.eventId)
    if existing:
        response.status_code = status.HTTP_200_OK
        return _to_response(existing)

    event = Event(
        event_id=payload.eventId,
        account_id=payload.accountId,
        type=payload.type,
        amount=payload.amount,
        currency=payload.currency,
        event_timestamp=payload.eventTimestamp,
        metadata_=payload.metadata,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return _to_response(event)


@router.get("/{event_id}", response_model=EventResponse)
def get_event(event_id: str, db: Session = Depends(get_db)):
    event = db.get(Event, event_id)
    if not event:
        raise HTTPException(status_code=404, detail=f"Event '{event_id}' not found")
    return _to_response(event)


@router.get("", response_model=PaginatedEventsResponse)
def list_events(
    account: str = Query(..., description="Account ID to filter by"),
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(20, ge=1, le=100, alias="pageSize", description="Items per page (max 100)"),
    db: Session = Depends(get_db),
):
    base_query = select(Event).where(Event.account_id == account)

    total = db.execute(select(func.count()).select_from(base_query.subquery())).scalar_one()

    events = (
        db.execute(
            base_query
            .order_by(Event.event_timestamp.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        .scalars()
        .all()
    )

    return PaginatedEventsResponse(
        data=[_to_response(e) for e in events],
        page=page,
        pageSize=page_size,
        total=total,
        totalPages=math.ceil(total / page_size) if total > 0 else 0,
    )
