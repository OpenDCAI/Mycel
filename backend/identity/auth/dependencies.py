"""Neutral auth dependency helpers."""

from fastapi import FastAPI, HTTPException


def _get_auth_service(app: FastAPI):
    auth_service = getattr(app.state, "auth_service", None)
    if auth_service is None:
        raise HTTPException(500, "Auth service not initialized")
    return auth_service
