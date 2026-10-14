import asyncio
import hashlib
import hmac
import importlib
import json

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import session as app_db
from app.db.base import Base
from app.models import Payment  # noqa: F401 - register tables before create_all

main_module = importlib.import_module("app.main")


@pytest.fixture
def api(tmp_path, monkeypatch):
    """Give each test its own SQLite database and run application startup."""
    engine = create_engine(f"sqlite:///{(tmp_path / 'payments.db').as_posix()}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(app_db, "SessionLocal", sessions)
    monkeypatch.setattr(main_module, "SessionLocal", sessions)
    monkeypatch.setenv("WEBHOOK_SECRET", "test-secret")

    async def startup():
        async with main_module.app.router.lifespan_context(main_module.app):
            pass

    asyncio.run(startup())

    def request(method, path, **kwargs):
        async def send():
            transport = httpx.ASGITransport(app=main_module.app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                return await client.request(method, path, **kwargs)

        return asyncio.run(send())

    yield request
    engine.dispose()


def payment_body(**overrides):
    body = {"tariff_id": "standard", "email": "student@example.com", "method": "card"}
    body.update(overrides)
    return body


def signed_webhook(api, payment_id, status, *, signature=None, raw_body=None):
    if raw_body is None:
        raw_body = json.dumps({"payment_id": payment_id, "status": status}).encode()
    if signature is None:
        signature = hmac.new(b"test-secret", raw_body, hashlib.sha256).hexdigest()
    return api(
        "POST",
        "/webhooks/bank",
        content=raw_body,
        headers={"X-Signature": signature, "Content-Type": "application/json"},
    )


def test_tariffs_are_seeded_with_prices_in_kopecks(api):
    response = api("GET", "/tariffs")

    assert response.status_code == 200
    assert response.json() == [
        {"id": "basic", "title": "Basic", "price": 990_000},
        {"id": "standard", "title": "Standard", "price": 1_990_000},
        {"id": "premium", "title": "Premium", "price": 2_990_000},
    ]


@pytest.mark.parametrize(
    ("promo_code", "expected_amount", "expected_discount"),
    [(None, 1_990_000, 0), ("KVITTO10", 1_791_000, 199_000), ("kvitto10", 1_791_000, 199_000)],
)
def test_payment_amount_and_case_insensitive_promo(
    api, promo_code, expected_amount, expected_discount
):
    body = payment_body()
    if promo_code is not None:
        body["promo_code"] = promo_code

    response = api("POST", "/payments", json=body)

    assert response.status_code == 201
    payment = response.json()
    assert payment["amount"] == expected_amount
    assert payment["discount"] == expected_discount
    assert payment["status"] == "pending"
    assert payment["method"] == "card"
    assert payment["schedule"] is None
    assert payment["installment_months"] is None
    assert payment["created_at"]


@pytest.mark.parametrize("months", [3, 6, 12])
def test_installment_schedule_preserves_every_kopeck(api, months):
    response = api(
        "POST",
        "/payments",
        json=payment_body(method="installment", installment_months=months),
    )

    assert response.status_code == 201
    payment = response.json()
    common, remainder = divmod(1_990_000, months)
    assert payment["schedule"] == [common + (index < remainder) for index in range(months)]
    assert len(payment["schedule"]) == months
    assert sum(payment["schedule"]) == payment["amount"] == 1_990_000


def test_idempotency_returns_original_without_creating_duplicate(api):
    headers = {"Idempotency-Key": "checkout-123"}
    first = api("POST", "/payments", json=payment_body(), headers=headers)
    second = api(
        "POST",
        "/payments",
        json=payment_body(tariff_id="premium", email="other@example.com"),
        headers=headers,
    )

    assert first.status_code == 201
    assert second.status_code == 200
    assert second.json() == first.json()
    listing = api("GET", "/payments")
    assert listing.status_code == 200
    assert listing.json() == [first.json()]


def test_allowed_transitions_and_conflict_preserve_status(api):
    created = api("POST", "/payments", json=payment_body()).json()
    payment_id = created["id"]

    invalid = signed_webhook(api, payment_id, "refunded")
    assert invalid.status_code == 409
    assert invalid.json() == {"error": "invalid_transition"}
    assert api("GET", f"/payments/{payment_id}").json()["status"] == "pending"

    succeeded = signed_webhook(api, payment_id, "succeeded")
    assert succeeded.status_code == 200
    assert succeeded.json() == {"result": "ok"}
    assert api("GET", f"/payments/{payment_id}").json()["status"] == "succeeded"

    duplicate = signed_webhook(api, payment_id, "succeeded")
    assert duplicate.status_code == 409
    assert duplicate.json() == {"error": "invalid_transition"}
    assert api("GET", f"/payments/{payment_id}").json()["status"] == "succeeded"

    refunded = signed_webhook(api, payment_id, "refunded")
    assert refunded.status_code == 200
    assert api("GET", f"/payments/{payment_id}").json()["status"] == "refunded"

    invalid_after_refund = signed_webhook(api, payment_id, "failed")
    assert invalid_after_refund.status_code == 409
    assert api("GET", f"/payments/{payment_id}").json()["status"] == "refunded"


def test_failed_payment_cannot_change_status(api):
    payment_id = api("POST", "/payments", json=payment_body()).json()["id"]

    assert signed_webhook(api, payment_id, "failed").status_code == 200
    invalid = signed_webhook(api, payment_id, "succeeded")

    assert invalid.status_code == 409
    assert invalid.json() == {"error": "invalid_transition"}
    assert api("GET", f"/payments/{payment_id}").json()["status"] == "failed"


def test_missing_payment_returns_404(api):
    assert api("GET", "/payments/12345").status_code == 404
    assert signed_webhook(api, 12345, "succeeded").status_code == 404


def test_webhook_rejects_invalid_signature_before_parsing_json(api):
    payment_id = api("POST", "/payments", json=payment_body()).json()["id"]

    invalid = signed_webhook(api, payment_id, "succeeded", signature="wrong")
    malformed = signed_webhook(
        api, payment_id, "succeeded", signature="wrong", raw_body=b"{invalid json"
    )
    valid_signature_malformed_body = signed_webhook(
        api, payment_id, "succeeded", raw_body=b"{invalid json"
    )

    assert invalid.status_code == 401
    assert malformed.status_code == 401
    assert valid_signature_malformed_body.status_code == 422
    assert api("GET", f"/payments/{payment_id}").json()["status"] == "pending"


def test_payment_filters_by_email_and_status(api):
    first = api("POST", "/payments", json=payment_body(email="a@example.com")).json()
    second = api("POST", "/payments", json=payment_body(email="b@example.com")).json()
    third = api("POST", "/payments", json=payment_body(email="a@example.com")).json()
    assert signed_webhook(api, second["id"], "succeeded").status_code == 200
    assert signed_webhook(api, third["id"], "failed").status_code == 200

    assert [p["id"] for p in api("GET", "/payments", params={"email": "a@example.com"}).json()] == [
        first["id"],
        third["id"],
    ]
    assert [p["id"] for p in api("GET", "/payments", params={"status": "succeeded"}).json()] == [
        second["id"]
    ]
    assert [
        p["id"]
        for p in api(
            "GET", "/payments", params={"email": "a@example.com", "status": "failed"}
        ).json()
    ] == [third["id"]]
    assert api("GET", "/payments", params={"status": "unknown"}).status_code == 422


@pytest.mark.parametrize(
    "overrides",
    [
        {"tariff_id": "unknown"},
        {"promo_code": "other"},
        {"method": "cash"},
        {"method": "installment"},
        {"method": "installment", "installment_months": 2},
        {"method": "card", "installment_months": 3},
        {"email": "not-an-email"},
    ],
)
def test_invalid_payment_input_returns_standard_422(api, overrides):
    response = api("POST", "/payments", json=payment_body(**overrides))

    assert response.status_code == 422
    assert isinstance(response.json()["detail"], list)
    assert api("GET", "/payments").json() == []
