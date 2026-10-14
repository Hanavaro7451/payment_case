from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy.exc import IntegrityError

from app.api import router
from app.db.session import SessionLocal
from app.services.tariff import TariffService


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    try:
        with SessionLocal.begin() as db:
            TariffService(db).seed_defaults()
    except IntegrityError:
        with SessionLocal() as db:
            if not TariffService(db).defaults_exist():
                raise
    yield


app = FastAPI(title="Квитто Payments API", lifespan=lifespan)
app.include_router(router)
