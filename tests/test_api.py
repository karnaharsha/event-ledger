"""
Tests covering idempotency, out-of-order events, balance computation, validation,
pagination, and concurrent duplicate submissions.
"""
import threading
from decimal import Decimal


BASE_EVENT = {
    "eventId": "evt-001",
    "accountId": "acct-123",
    "type": "CREDIT",
    "amount": 150.00,
    "currency": "USD",
    "eventTimestamp": "2026-05-15T14:02:11Z",
    "metadata": {"source": "mainframe-batch", "batchId": "B-9042"},
}


# ---------------------------------------------------------------------------
# Submit & retrieve
# ---------------------------------------------------------------------------

class TestSubmitEvent:
    def test_create_event_returns_201(self, client):
        resp = client.post("/events", json=BASE_EVENT)
        assert resp.status_code == 201
        data = resp.json()
        assert data["eventId"] == "evt-001"
        assert data["accountId"] == "acct-123"
        assert data["type"] == "CREDIT"
        assert Decimal(str(data["amount"])) == Decimal("150.0")

    def test_get_event_by_id(self, client):
        client.post("/events", json=BASE_EVENT)
        resp = client.get("/events/evt-001")
        assert resp.status_code == 200
        assert resp.json()["eventId"] == "evt-001"

    def test_get_nonexistent_event_returns_404(self, client):
        resp = client.get("/events/nonexistent")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------

class TestIdempotency:
    def test_duplicate_submission_returns_200(self, client):
        client.post("/events", json=BASE_EVENT)
        resp = client.post("/events", json=BASE_EVENT)
        assert resp.status_code == 200

    def test_duplicate_submission_does_not_alter_balance(self, client):
        client.post("/events", json=BASE_EVENT)
        client.post("/events", json=BASE_EVENT)
        client.post("/events", json=BASE_EVENT)
        resp = client.get("/accounts/acct-123/balance")
        assert resp.status_code == 200
        assert Decimal(str(resp.json()["balance"])) == Decimal("150.0")

    def test_duplicate_returns_original_event(self, client):
        first = client.post("/events", json=BASE_EVENT).json()
        second = client.post("/events", json=BASE_EVENT).json()
        assert first["receivedAt"] == second["receivedAt"]

    def test_different_event_ids_are_independent(self, client):
        client.post("/events", json={**BASE_EVENT, "eventId": "evt-A"})
        resp = client.post("/events", json={**BASE_EVENT, "eventId": "evt-B"})
        assert resp.status_code == 201


# ---------------------------------------------------------------------------
# Out-of-order tolerance
# ---------------------------------------------------------------------------

class TestOutOfOrder:
    def test_listing_ordered_by_event_timestamp(self, client):
        events = [
            {**BASE_EVENT, "eventId": "evt-late", "eventTimestamp": "2026-05-15T16:00:00Z"},
            {**BASE_EVENT, "eventId": "evt-early", "eventTimestamp": "2026-05-15T10:00:00Z"},
            {**BASE_EVENT, "eventId": "evt-mid", "eventTimestamp": "2026-05-15T12:00:00Z"},
        ]
        for e in events:
            client.post("/events", json=e)

        resp = client.get("/events", params={"account": "acct-123"})
        assert resp.status_code == 200
        timestamps = [e["eventTimestamp"] for e in resp.json()["data"]]
        assert timestamps == sorted(timestamps)

    def test_balance_correct_regardless_of_arrival_order(self, client):
        # Arrive in reverse chronological order
        client.post("/events", json={**BASE_EVENT, "eventId": "evt-3", "type": "DEBIT",  "amount": 50.00, "eventTimestamp": "2026-05-15T15:00:00Z"})
        client.post("/events", json={**BASE_EVENT, "eventId": "evt-2", "type": "CREDIT", "amount": 200.00, "eventTimestamp": "2026-05-15T12:00:00Z"})
        client.post("/events", json={**BASE_EVENT, "eventId": "evt-1", "type": "CREDIT", "amount": 100.00, "eventTimestamp": "2026-05-15T09:00:00Z"})

        resp = client.get("/accounts/acct-123/balance")
        assert resp.status_code == 200
        # 100 + 200 - 50 = 250
        assert Decimal(str(resp.json()["balance"])) == Decimal("250.0")


# ---------------------------------------------------------------------------
# Balance computation
# ---------------------------------------------------------------------------

class TestBalance:
    def test_balance_credits_only(self, client):
        client.post("/events", json={**BASE_EVENT, "eventId": "c1", "type": "CREDIT", "amount": 100})
        client.post("/events", json={**BASE_EVENT, "eventId": "c2", "type": "CREDIT", "amount": 250})
        resp = client.get("/accounts/acct-123/balance")
        assert Decimal(str(resp.json()["balance"])) == Decimal("350")

    def test_balance_debits_only(self, client):
        client.post("/events", json={**BASE_EVENT, "eventId": "d1", "type": "DEBIT", "amount": 75})
        resp = client.get("/accounts/acct-123/balance")
        assert Decimal(str(resp.json()["balance"])) == Decimal("-75")

    def test_balance_mixed(self, client):
        client.post("/events", json={**BASE_EVENT, "eventId": "m1", "type": "CREDIT", "amount": 500})
        client.post("/events", json={**BASE_EVENT, "eventId": "m2", "type": "DEBIT",  "amount": 200})
        client.post("/events", json={**BASE_EVENT, "eventId": "m3", "type": "DEBIT",  "amount": 50})
        resp = client.get("/accounts/acct-123/balance")
        assert Decimal(str(resp.json()["balance"])) == Decimal("250")

    def test_balance_unknown_account_returns_404(self, client):
        resp = client.get("/accounts/ghost-acct/balance")
        assert resp.status_code == 404

    def test_balance_decimal_precision(self, client):
        client.post("/events", json={**BASE_EVENT, "eventId": "p1", "type": "CREDIT", "amount": 0.10})
        client.post("/events", json={**BASE_EVENT, "eventId": "p2", "type": "CREDIT", "amount": 0.20})
        resp = client.get("/accounts/acct-123/balance")
        # Should be exactly 0.30, not 0.30000000000000004
        assert Decimal(str(resp.json()["balance"])) == Decimal("0.30")


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

class TestValidation:
    def test_missing_event_id(self, client):
        payload = {k: v for k, v in BASE_EVENT.items() if k != "eventId"}
        resp = client.post("/events", json=payload)
        assert resp.status_code == 422

    def test_missing_account_id(self, client):
        payload = {k: v for k, v in BASE_EVENT.items() if k != "accountId"}
        resp = client.post("/events", json=payload)
        assert resp.status_code == 422

    def test_missing_type(self, client):
        payload = {k: v for k, v in BASE_EVENT.items() if k != "type"}
        resp = client.post("/events", json=payload)
        assert resp.status_code == 422

    def test_invalid_type(self, client):
        resp = client.post("/events", json={**BASE_EVENT, "type": "TRANSFER"})
        assert resp.status_code == 422

    def test_zero_amount(self, client):
        resp = client.post("/events", json={**BASE_EVENT, "amount": 0})
        assert resp.status_code == 422

    def test_negative_amount(self, client):
        resp = client.post("/events", json={**BASE_EVENT, "amount": -50})
        assert resp.status_code == 422

    def test_missing_amount(self, client):
        payload = {k: v for k, v in BASE_EVENT.items() if k != "amount"}
        resp = client.post("/events", json=payload)
        assert resp.status_code == 422

    def test_missing_currency(self, client):
        payload = {k: v for k, v in BASE_EVENT.items() if k != "currency"}
        resp = client.post("/events", json=payload)
        assert resp.status_code == 422

    def test_missing_timestamp(self, client):
        payload = {k: v for k, v in BASE_EVENT.items() if k != "eventTimestamp"}
        resp = client.post("/events", json=payload)
        assert resp.status_code == 422

    def test_metadata_is_optional(self, client):
        payload = {k: v for k, v in BASE_EVENT.items() if k != "metadata"}
        resp = client.post("/events", json=payload)
        assert resp.status_code == 201

    def test_list_events_requires_account_param(self, client):
        resp = client.get("/events")
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------

class TestPagination:
    def _seed(self, client, n: int):
        for i in range(n):
            client.post("/events", json={
                **BASE_EVENT,
                "eventId": f"pg-evt-{i:03d}",
                "eventTimestamp": f"2026-05-15T{9 + i // 60:02d}:{i % 60:02d}:00Z",
            })

    def test_pagination_metadata_present(self, client):
        self._seed(client, 5)
        resp = client.get("/events", params={"account": "acct-123"})
        data = resp.json()
        assert "data" in data
        assert "total" in data
        assert "page" in data
        assert "pageSize" in data
        assert "totalPages" in data

    def test_default_page_returns_first_20(self, client):
        self._seed(client, 25)
        resp = client.get("/events", params={"account": "acct-123"})
        data = resp.json()
        assert data["page"] == 1
        assert data["pageSize"] == 20
        assert data["total"] == 25
        assert data["totalPages"] == 2
        assert len(data["data"]) == 20

    def test_second_page_returns_remainder(self, client):
        self._seed(client, 25)
        resp = client.get("/events", params={"account": "acct-123", "page": 2, "pageSize": 20})
        data = resp.json()
        assert data["page"] == 2
        assert len(data["data"]) == 5

    def test_custom_page_size(self, client):
        self._seed(client, 10)
        resp = client.get("/events", params={"account": "acct-123", "pageSize": 3})
        data = resp.json()
        assert len(data["data"]) == 3
        assert data["totalPages"] == 4  # ceil(10/3)

    def test_page_beyond_total_returns_empty(self, client):
        self._seed(client, 5)
        resp = client.get("/events", params={"account": "acct-123", "page": 99})
        data = resp.json()
        assert data["data"] == []
        assert data["total"] == 5

    def test_page_size_exceeds_max_is_rejected(self, client):
        resp = client.get("/events", params={"account": "acct-123", "pageSize": 999})
        assert resp.status_code == 422

    def test_pagination_preserves_chronological_order(self, client):
        self._seed(client, 10)
        p1 = client.get("/events", params={"account": "acct-123", "pageSize": 5, "page": 1}).json()["data"]
        p2 = client.get("/events", params={"account": "acct-123", "pageSize": 5, "page": 2}).json()["data"]
        all_ts = [e["eventTimestamp"] for e in p1 + p2]
        assert all_ts == sorted(all_ts)


# ---------------------------------------------------------------------------
# Concurrency
# ---------------------------------------------------------------------------

class TestConcurrency:
    def test_concurrent_duplicate_posts_create_only_one_event(self, client):
        """
        Fire 10 threads simultaneously with the same eventId.
        Exactly one should get 201; the rest should get 200.
        The balance must reflect the event amount only once.
        """
        results = []
        lock = threading.Lock()

        def post():
            resp = client.post("/events", json={**BASE_EVENT, "eventId": "concurrent-evt"})
            with lock:
                results.append(resp.status_code)

        threads = [threading.Thread(target=post) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert results.count(201) == 1
        assert results.count(200) == 9

        balance = client.get("/accounts/acct-123/balance").json()["balance"]
        assert Decimal(str(balance)) == Decimal(str(BASE_EVENT["amount"]))
