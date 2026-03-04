"""Pydantic request models for Leon web API."""

from pydantic import BaseModel


class CreateThreadRequest(BaseModel):
    sandbox: str = "local"
    cwd: str | None = None
    model: str | None = None
    mode: str = "normal"


class RunRequest(BaseModel):
    message: str
    enable_trajectory: bool = False
    model: str | None = None


class SendMessageRequest(BaseModel):
    message: str


class TaskAgentRequest(BaseModel):
    subagent_type: str
    prompt: str
    description: str | None = None
    model: str | None = None
    max_turns: int | None = None
