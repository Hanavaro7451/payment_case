import hashlib
import hmac

from fastapi import APIRouter, Header, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from app.api.dependencies import SessionDep
from app.core.config import get_webhook_secret
from app.domain.payment import PaymentStatus
from app.models.payment import Payment
from app.schemas.payment import BankWebhook, PaymentCreate, PaymentOut, WebhookResult
from app.services.payment import (
    InvalidTransitionError,
    PaymentNotFoundError,
    PaymentService,
    UnknownTariffError,
)

router = APIRouter()


def validation_error(field: str, value: object, message: str) -> RequestValidationError:
    return RequestValidationError(
        [{"type": "value_error", "loc": ("body", field), "msg": message, "input": value}]
    )


def parse_webhook_body(raw_body: bytes) -> BankWebhook:
    """Keep Pydantic errors in FastAPI's usual 422 response shape."""
    try:
        return BankWebhook.model_validate_json(raw_body)
    except ValidationError as exc:
        errors = []
        for error in exc.errors():
            detail = {key: value for key, value in error.items() if key != "ctx"}
            detail["loc"] = ("body", *error["loc"])
            if isinstance(detail.get("input"), bytes):
                detail["input"] = detail["input"].decode("utf-8", errors="replace")
            errors.append(detail)
        raise RequestValidationError(errors) from exc


@router.post("/payments", response_model=PaymentOut, status_code=201)
def create_payment(
    body: PaymentCreate,
    response: Response,
    db: SessionDep,
    idempotency_key: str | None = Header(default=None, min_length=1, max_length=255),
) -> Payment:
    try:
        payment, created = PaymentService(db).create(body, idempotency_key)
    except UnknownTariffError as exc:
        raise validation_error("tariff_id", body.tariff_id, "Unknown tariff_id") from exc
    if not created:
        response.status_code = 200
    return payment


@router.get("/payments", response_model=list[PaymentOut])
def list_payments(
    db: SessionDep,
    email: str | None = None,
    status: PaymentStatus | None = None,
) -> list[Payment]:
    return PaymentService(db).list_payments(email, status)


@router.get("/payments/{payment_id}", response_model=PaymentOut)
def get_payment(payment_id: int, db: SessionDep) -> Payment:
    try:
        return PaymentService(db).get(payment_id)
    except PaymentNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Payment not found") from exc


@router.post("/webhooks/bank", response_model=WebhookResult)
async def bank_webhook(
    request: Request,
    db: SessionDep,
    x_signature: str | None = Header(default=None),
) -> WebhookResult | JSONResponse:
    secret = get_webhook_secret()
    if not secret:
        raise HTTPException(status_code=503, detail="WEBHOOK_SECRET is not configured")

    raw_body = await request.body()
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    if not x_signature or not hmac.compare_digest(x_signature, expected):
        raise HTTPException(status_code=401, detail="Invalid signature")

    body = parse_webhook_body(raw_body)
    try:
        PaymentService(db).transition(body.payment_id, body.status)
    except PaymentNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Payment not found") from exc
    except InvalidTransitionError:
        return JSONResponse(status_code=409, content={"error": "invalid_transition"})
    return WebhookResult()
