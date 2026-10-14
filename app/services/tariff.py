from sqlalchemy.orm import Session

from app.models.tariff import Tariff
from app.repositories.tariff import TariffRepository

DEFAULT_TARIFFS = (
    ("basic", "Basic", 990_000),
    ("standard", "Standard", 1_990_000),
    ("premium", "Premium", 2_990_000),
)


class TariffService:
    def __init__(self, db: Session) -> None:
        self.tariffs = TariffRepository(db)

    def list_all(self) -> list[Tariff]:
        return self.tariffs.list_all()

    def seed_defaults(self) -> None:
        self.tariffs.seed_missing(DEFAULT_TARIFFS)

    def defaults_exist(self) -> bool:
        return all(self.tariffs.get(tariff_id) is not None for tariff_id, _, _ in DEFAULT_TARIFFS)
