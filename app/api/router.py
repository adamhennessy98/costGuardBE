from fastapi import APIRouter

from app.api.routes import invoices, items, vendors

api_router = APIRouter()
api_router.include_router(items.router)
api_router.include_router(invoices.router)
api_router.include_router(vendors.router)
