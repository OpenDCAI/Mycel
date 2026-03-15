"""Pydantic request models for Leon web API."""

from pydantic import BaseModel


class CreateThreadRequest(BaseModel):
    sandbox: str = "local"
    cwd: str | None = None
    model: str | None = None
    agent: str | None = None



class SendMessageRequest(BaseModel):
    message: str

