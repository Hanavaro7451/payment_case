from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domain.payment import ALLOWED_TRANSITIONS, PaymentStatus, installment_schedule
from app.models.payment import Payment
from app.repositories.payment import PaymentRepository
from app.repositories.tariff import TariffRepository
from app.schemas.payment import PaymentCreate


class UnknownTariffError(Exception):
    pass


class PaymentNotFoundError(Exception):
    pass


class InvalidTransitionError(Exception):
    pass


class PaymentService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.payments = PaymentRepository(db)
        self.tariffs = TariffRepository(db)

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
