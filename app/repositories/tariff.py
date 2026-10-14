from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.tariff import Tariff


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
