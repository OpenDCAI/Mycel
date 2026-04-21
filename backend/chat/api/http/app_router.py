"""Aggregate HTTP router for the chat backend."""

from fastapi import APIRouter

from backend.chat.api.http import (
    conversations_router,
    relationships_router,
)
from backend.chat.api.http import (
    router as messaging_router,
)

router = APIRouter()

router.include_router(messaging_router.router)
router.include_router(relationships_router.router)
router.include_router(conversations_router.router)
