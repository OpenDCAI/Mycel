"""Neutral auth dependency helpers."""

from fastapi import FastAPI, HTTPException


def _get_auth_service(app: FastAPI):
    runtime_state = getattr(app.state, "auth_runtime_state", None)
    auth_service = getattr(runtime_state, "auth_service", None)
    if auth_service is None:
        raise HTTPException(500, "Auth service not initialized")
    return auth_service
