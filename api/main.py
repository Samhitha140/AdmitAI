"""
FastAPI entrypoint for IntelliAdmit.

    uvicorn api.main:app --reload

Configures LangSmith tracing (if keys present) and mounts the chat routes.
"""
from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import router
from config.settings import settings

# enable LangSmith tracing when configured
if settings.LANGSMITH_API_KEY:
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_PROJECT"] = settings.LANGCHAIN_PROJECT

app = FastAPI(
    title="IntelliAdmit API",
    description="Agentic AI University Admission Counsellor",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")


@app.get("/")
async def root() -> dict:
    return {"service": "IntelliAdmit", "mode": settings.mode, "docs": "/docs"}
