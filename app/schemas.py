"""API input and output shapes."""

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator


class PaymentMethod(StrEnum):
    card = "card"
    sbp = "sbp"
    installment = "installment"


class PaymentStatus(StrEnum):
    pending = "pending"
    succeeded = "succeeded"
    failed = "failed"
    refunded = "refunded"


class TariffOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    price: int


class PaymentCreate(BaseModel):
    tariff_id: str
    email: EmailStr
    method: PaymentMethod
    installment_months: Literal[3, 6, 12] | None = None
    promo_code: str | None = None

    @model_validator(mode="after")
    def validate_payment_options(self) -> "PaymentCreate":
        if self.method == PaymentMethod.installment and self.installment_months is None:
            raise ValueError("installment_months is required for installment")
        if self.method != PaymentMethod.installment and self.installment_months is not None:
            raise ValueError("installment_months is only allowed for installment")
        if self.promo_code is not None:
            if self.promo_code.upper() != "KVITTO10":
                raise ValueError("Unknown promo_code")
            self.promo_code = "KVITTO10"
        return self


class PaymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: PaymentStatus
    tariff_id: str
    amount: int
    discount: int
    method: PaymentMethod
    installment_months: int | None
    schedule: list[int] | None
    email: EmailStr
    created_at: datetime


class BankWebhook(BaseModel):
    payment_id: int = Field(gt=0)
    status: PaymentStatus


class WebhookResult(BaseModel):
    result: Literal["ok"] = "ok"
