# Event Ledger API

A financial transaction event ledger that handles **idempotent** event submission and **out-of-order** event arrival.

## Stack

- **Framework:** FastAPI (Python 3.11+)
- **Database:** SQLite via SQLAlchemy (embedded, no external setup)
- **Tests:** pytest + FastAPI TestClient

---

## Prerequisites

- Python 3.11 or later
- `pip` (or `pip3`)

---

## Setup

```bash
cd event-ledger

# Create and activate a virtual environment (recommended)
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

---

## Run the application

```bash
uvicorn app.main:app --reload
```

The API will be available at **http://localhost:8000**.

Interactive API docs (Swagger UI): **http://localhost:8000/docs**

---

## Run the tests

```bash
pytest -v
```

Tests use a fully in-memory SQLite database — no files are created or left behind.

---

## API Reference

### `POST /events`

Submit a transaction event. Idempotent: submitting the same `eventId` twice returns the original event with `200 OK` (no duplicate is created).

**Request body:**
```json
{
  "eventId": "evt-001",
  "accountId": "acct-123",
  "type": "CREDIT",
  "amount": 150.00,
  "currency": "USD",
  "eventTimestamp": "2026-05-15T14:02:11Z",
  "metadata": {
    "source": "mainframe-batch",
    "batchId": "B-9042"
  }
}
```

| Status | Meaning |
|--------|---------|
| `201 Created` | New event accepted |
| `200 OK` | Duplicate — original event returned |
| `422 Unprocessable Entity` | Validation error |

---

### `GET /events/{id}`

Retrieve a single event by its ID.

| Status | Meaning |
|--------|---------|
| `200 OK` | Event found |
| `404 Not Found` | No event with that ID |

---

### `GET /events?account={accountId}`

List all events for an account, ordered by `eventTimestamp` ascending (chronological), regardless of the order they were received.

| Status | Meaning |
|--------|---------|
| `200 OK` | Array of events (may be empty) |
| `422 Unprocessable Entity` | Missing `account` query parameter |

---

### `GET /accounts/{accountId}/balance`

Returns the net balance for an account:

```
balance = sum(CREDIT amounts) - sum(DEBIT amounts)
```

| Status | Meaning |
|--------|---------|
| `200 OK` | Balance returned |
| `404 Not Found` | No events found for this account |

---

## Design notes

- **Idempotency** is enforced at the database layer by making `eventId` the primary key. A `GET` on the existing row is attempted before any `INSERT`.
- **Out-of-order tolerance** is achieved by storing the original `eventTimestamp` and always sorting by it on read — arrival order is irrelevant.
- **Decimal precision** — amounts are stored as `NUMERIC(18, 6)` and handled as Python `Decimal` throughout to avoid floating-point drift.
- **Concurrency** — SQLite serializes writes by default, so concurrent duplicate submissions for the same `eventId` are safe; the second writer will find the row already committed.
