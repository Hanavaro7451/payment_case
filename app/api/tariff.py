from fastapi import APIRouter

from app.api.dependencies import SessionDep
from app.models.tariff import Tariff
from app.schemas.tariff import TariffOut
from app.services.tariff import TariffService

router = APIRouter()


@router.get("/tariffs", response_model=list[TariffOut])
def list_tariffs(db: SessionDep) -> list[Tariff]:
    return TariffService(db).list_all()
