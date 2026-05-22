from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from .database import Base, engine
from .routers import accounts, events

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Event Ledger API",
    description="Financial transaction event ledger with idempotency and out-of-order tolerance",
    version="1.0.0",
)

app.include_router(events.router)
app.include_router(accounts.router)


@app.exception_handler(ValidationError)
async def validation_exception_handler(request, exc):
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors()},
    )


@app.get("/health")
def health():
    return {"status": "ok"}
