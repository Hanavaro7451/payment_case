"""Payment rules independent from HTTP and SQL query details."""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Payment, Tariff
from app.repositories import PaymentRepository, TariffRepository
from app.schemas import PaymentCreate, PaymentStatus

DEFAULT_TARIFFS = (
    ("basic", "Basic", 990_000),
    ("standard", "Standard", 1_990_000),
    ("premium", "Premium", 2_990_000),
)

ALLOWED_TRANSITIONS = {
    PaymentStatus.pending: {PaymentStatus.succeeded, PaymentStatus.failed},
    PaymentStatus.succeeded: {PaymentStatus.refunded},
}


class UnknownTariffError(Exception):
    pass


class PaymentNotFoundError(Exception):
    pass


class InvalidTransitionError(Exception):
    pass


def installment_schedule(amount: int, months: int) -> list[int]:
    """Put remainder kopecks into the earliest installments."""
    common, remainder = divmod(amount, months)
    return [common + (index < remainder) for index in range(months)]


class PaymentService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.payments = PaymentRepository(db)
        self.tariffs = TariffRepository(db)

    def list_tariffs(self) -> list[Tariff]:
        return self.tariffs.list_all()

    def list_payments(self, email: str | None, status: PaymentStatus | None) -> list[Payment]:
        return self.payments.list_filtered(email, status)

    def create(self, data: PaymentCreate, idempotency_key: str | None) -> tuple[Payment, bool]:
        """Return (payment, created); the same key always returns the first payment."""
        if idempotency_key is not None:
            existing = self.payments.get_by_idempotency_key(idempotency_key)
            if existing is not None:
                return existing, False

        tariff = self.tariffs.get(data.tariff_id)
        if tariff is None:
            raise UnknownTariffError(data.tariff_id)

        discount = tariff.price // 10 if data.promo_code else 0
        amount = tariff.price - discount
        payment = Payment(
            status=PaymentStatus.pending.value,
            tariff_id=tariff.id,
            amount=amount,
            discount=discount,
            method=data.method.value,
            installment_months=data.installment_months,
            schedule=(
                installment_schedule(amount, data.installment_months)
                if data.installment_months is not None
                else None
            ),
            email=str(data.email),
            idempotency_key=idempotency_key,
        )
        try:
            return self.payments.save(payment), True
        except IntegrityError:
            self.db.rollback()
            if idempotency_key is None:
                raise
            existing = self.payments.get_by_idempotency_key(idempotency_key)
            if existing is None:
                raise
            return existing, False

    def get(self, payment_id: int) -> Payment:
        payment = self.payments.get(payment_id)
        if payment is None:
            raise PaymentNotFoundError(payment_id)
        return payment

    def transition(self, payment_id: int, target: PaymentStatus) -> None:
        payment = self.get(payment_id)
        current = PaymentStatus(payment.status)
        if target not in ALLOWED_TRANSITIONS.get(current, set()):
            raise InvalidTransitionError
        if not self.payments.compare_and_set_status(payment_id, current, target):
            raise InvalidTransitionError
