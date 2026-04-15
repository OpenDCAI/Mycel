"""Debug logging endpoints."""

import tempfile
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api/debug", tags=["debug"])


class LogMessage(BaseModel):
    message: str
    timestamp: str


def _debug_log_path() -> Path:
    return Path(tempfile.gettempdir()) / "leon-frontend-console.log"


@router.post("/log")
async def log_frontend_message(payload: LogMessage) -> dict:
    """Receive frontend console logs and write to file."""
    log_path = _debug_log_path()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as f:
        f.write(f"[{payload.timestamp}] {payload.message}\n")
    return {"status": "ok"}
