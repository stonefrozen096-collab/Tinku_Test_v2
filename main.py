"""
Tinku AI Agent v2 — Production FastAPI Backend
Stack: FastAPI + MongoDB + Gemini/Groq/Claude + Google OAuth
Deploy: Render.com
"""

from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import os
import json
import asyncio
from datetime import datetime

from database import db_client, get_db
from routers import auth, chat, users
from config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await db_client.connect()
    print("✅ MongoDB connected")
    yield
    # Shutdown
    await db_client.disconnect()
    print("👋 MongoDB disconnected")


app = FastAPI(
    title="Tinku AI Agent",
    description="Your personal AI agent powered by Gemini, Groq & Claude",
    version="2.0.0",
    lifespan=lifespan
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(chat.router, prefix="/api/chat", tags=["chat"])
app.include_router(users.router, prefix="/api/users", tags=["users"])

# Phase 6 — Export & Maintenance
from export_router import router as export_router
app.include_router(export_router, prefix="/api", tags=["export"])

@app.get("/api/status")
async def get_status():
    maintenance = os.getenv("MAINTENANCE_MODE", "false").lower() == "true"
    return JSONResponse({"maintenance": maintenance})

# Serve static files
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/", response_class=HTMLResponse)
async def serve_app():
    with open("static/index.html", "r") as f:
        return f.read()


@app.get("/health")
async def health():
    return {"status": "ok", "version": "2.0.0", "agent": "Tinku"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.environ.get("PORT", 8000)), reload=True)
