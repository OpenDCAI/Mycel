"""Minimal lifespan for the separate Monitor app shell."""

from contextlib import asynccontextmanager

from fastapi import FastAPI


@asynccontextmanager
async def lifespan(_app: FastAPI):
    yield
