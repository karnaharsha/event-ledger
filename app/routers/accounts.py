from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Event
from ..schemas import BalanceResponse

router = APIRouter(prefix="/accounts", tags=["accounts"])


@router.get("/{account_id}/balance", response_model=BalanceResponse)
def get_balance(account_id: str, db: Session = Depends(get_db)):
    result = db.execute(
        select(
            func.sum(
                case(
                    (Event.type == "CREDIT", Event.amount),
                    else_=-Event.amount,
                )
            ).label("balance"),
            func.max(Event.currency).label("currency"),
            func.count().label("event_count"),
        ).where(Event.account_id == account_id)
    ).one()

    if result.event_count == 0:
        raise HTTPException(status_code=404, detail=f"Account '{account_id}' not found")

    balance = Decimal(str(result.balance)) if result.balance is not None else Decimal("0")

    return BalanceResponse(
        accountId=account_id,
        balance=balance,
        currency=result.currency,
    )
