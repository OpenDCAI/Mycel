from fastapi import APIRouter

from backend.chat.api.http import (
    chats_router,
    conversations_router,
    internal_identity_router,
    internal_messaging_router,
    relationships_router,
)

router = APIRouter()

router.include_router(chats_router.router)
router.include_router(internal_identity_router.router)
router.include_router(internal_messaging_router.router)
router.include_router(relationships_router.router)
router.include_router(conversations_router.router)
