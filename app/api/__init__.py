from fastapi import APIRouter

from app.api.payment import router as payment_router
from app.api.tariff import router as tariff_router

router = APIRouter()
router.include_router(tariff_router)
router.include_router(payment_router)
