from enum import StrEnum


class PaymentMethod(StrEnum):
    card = "card"
    sbp = "sbp"
    installment = "installment"


class PaymentStatus(StrEnum):
    pending = "pending"
    succeeded = "succeeded"
    failed = "failed"
    refunded = "refunded"


ALLOWED_TRANSITIONS = {
    PaymentStatus.pending: {PaymentStatus.succeeded, PaymentStatus.failed},
    PaymentStatus.succeeded: {PaymentStatus.refunded},
}


def installment_schedule(amount: int, months: int) -> list[int]:
    common, remainder = divmod(amount, months)
    return [common + (index < remainder) for index in range(months)]
