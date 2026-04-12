from fastapi import APIRouter

from src.api.health import router as health_router
from src.api.v1.auth import router as auth_router
from src.api.v1.checkout import router as checkout_router
from src.api.v1.orders import router as orders_router

router = APIRouter()
router.include_router(health_router)
router.include_router(checkout_router)
router.include_router(auth_router)
router.include_router(orders_router)
