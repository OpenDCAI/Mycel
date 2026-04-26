from fastapi import APIRouter

from backend.chat.api.http import (
    chats_router,
    conversations_router,
    relationships_router,
    runtime_inbox_router,
)

router = APIRouter()

router.include_router(chats_router.router)
router.include_router(relationships_router.router)
router.include_router(conversations_router.router)
router.include_router(runtime_inbox_router.router)
