from fastapi import APIRouter

from backend.api import catalog, downloads, history, library, system

router = APIRouter()
for module in (system, catalog, downloads, library, history):
    router.include_router(module.router)

__all__ = ["router"]
