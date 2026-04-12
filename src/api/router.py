from fastapi import APIRouter

from src.api.v1.checkout import router as checkout_router

router = APIRouter()
router.include_router(checkout_router)
