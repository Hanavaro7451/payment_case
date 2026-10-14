"""SQLAlchemy queries used by the payment service."""

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import Payment, Tariff
from app.schemas import PaymentStatus


class TariffRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_all(self) -> list[Tariff]:
        return list(self.db.scalars(select(Tariff).order_by(Tariff.price)))

    def get(self, tariff_id: str) -> Tariff | None:
        return self.db.get(Tariff, tariff_id)

    def seed_missing(self, defaults: tuple[tuple[str, str, int], ...]) -> None:
        for tariff_id, title, price in defaults:
            if self.get(tariff_id) is None:
                self.db.add(Tariff(id=tariff_id, title=title, price=price))


class PaymentRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, payment_id: int) -> Payment | None:
        return self.db.get(Payment, payment_id)

    def get_by_idempotency_key(self, key: str) -> Payment | None:
        return self.db.scalar(select(Payment).where(Payment.idempotency_key == key))

    def list_filtered(self, email: str | None, status: PaymentStatus | None) -> list[Payment]:
        query = select(Payment).order_by(Payment.id)
        if email is not None:
            query = query.where(Payment.email == email)
        if status is not None:
            query = query.where(Payment.status == status.value)
        return list(self.db.scalars(query))

    def save(self, payment: Payment) -> Payment:
        self.db.add(payment)
        self.db.commit()
        self.db.refresh(payment)
        return payment

    def compare_and_set_status(
        self, payment_id: int, current: PaymentStatus, target: PaymentStatus
    ) -> bool:
        result = self.db.execute(
            update(Payment)
            .where(Payment.id == payment_id, Payment.status == current.value)
            .values(status=target.value)
        )
        if result.rowcount != 1:
            self.db.rollback()
            return False
        self.db.commit()
        return True
