"""Application setup and startup tariff seed."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy.exc import IntegrityError

from app.api import router
from app.db import SessionLocal
from app.repositories import TariffRepository
from app.services import DEFAULT_TARIFFS


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    try:
        with SessionLocal.begin() as db:
            TariffRepository(db).seed_missing(DEFAULT_TARIFFS)
    except IntegrityError:
        # Another worker may have seeded the same tariffs concurrently.
        with SessionLocal() as db:
            tariffs = TariffRepository(db)
            if any(tariffs.get(tariff_id) is None for tariff_id, _, _ in DEFAULT_TARIFFS):
                raise
    yield


app = FastAPI(title="Квитто Payments API", lifespan=lifespan)
app.include_router(router)
