"""Aggregate HTTP router for the chat backend."""

from fastapi import APIRouter

from backend.chat.api.http import (
    chat_candidates_router,
    chats_router,
    contacts_router,
    conversations_router,
    internal_messaging_router,
    internal_realtime_router,
    relationships_router,
)

router = APIRouter()

router.include_router(chats_router.router)
router.include_router(internal_messaging_router.router)
router.include_router(internal_realtime_router.router)
router.include_router(relationships_router.router)
router.include_router(conversations_router.router)
router.include_router(contacts_router.router)
router.include_router(chat_candidates_router.router)
