"""Aggregate HTTP router for the threads backend."""

from fastapi import APIRouter

from backend.threads.api.http import (
    internal_agent_actor_router,
    internal_runtime_read_router,
    owner_router,
    runtime_gateway_router,
    runtime_router,
)
from backend.web.routers import thread_files

router = APIRouter()

router.include_router(owner_router.router)
router.include_router(runtime_router.router)
router.include_router(runtime_gateway_router.router)
router.include_router(internal_agent_actor_router.router)
router.include_router(internal_runtime_read_router.router)
router.include_router(thread_files.router)
router.include_router(thread_files._public)
