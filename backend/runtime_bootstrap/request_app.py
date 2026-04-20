"""Neutral request->app dependency helper."""

from fastapi import FastAPI, Request


async def get_app(request: Request) -> FastAPI:
    return request.app
