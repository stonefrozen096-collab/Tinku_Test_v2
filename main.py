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


# ── Phase 9: Memory API ──
from memory import get_memory_summary
from routers.auth import get_current_user as _get_user

@app.get("/api/memory")
async def get_memory(request: Request, db=Depends(get_db)):
    user = _get_user(request)
    if not user or user.get("is_guest"):
        return {"memories": {}, "recent_topics": [], "total": 0}
    summary = await get_memory_summary(db, user["user_id"])
    return summary

@app.delete("/api/memory/{key}")
async def delete_memory_key(key: str, request: Request, db=Depends(get_db)):
    user = _get_user(request)
    if not user or user.get("is_guest"):
        raise HTTPException(status_code=401)
    await db.memories.delete_one({"user_id": user["user_id"], "key": key})
    return {"success": True}

@app.delete("/api/memory")
async def clear_memory(request: Request, db=Depends(get_db)):
    user = _get_user(request)
    if not user or user.get("is_guest"):
        raise HTTPException(status_code=401)
    await db.memories.delete_many({"user_id": user["user_id"]})
    await db.memory_topics.delete_many({"user_id": user["user_id"]})
    return {"success": True}

# ── Beta Code API ──
from beta_codes import redeem_beta_code, create_beta_code

@app.post("/api/beta/redeem")
async def redeem_code(request: Request, db=Depends(get_db)):
    user = get_current_user(request)
    if not user or user.get("is_guest"):
        raise HTTPException(status_code=401)
    body = await request.json()
    code = body.get("code", "")
    if not code:
        raise HTTPException(status_code=400, detail="Code required")
    try:
        result = await redeem_beta_code(db, user["user_id"], code)
        return result
    except Exception as e:
        print(f"[BETA REDEEM ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/beta/status")
async def beta_status(request: Request, db=Depends(get_db)):
    user = get_current_user(request)
    if not user or user.get("is_guest"):
        return {"is_beta": False}
    u = await db.users.find_one({"user_id": user["user_id"]})
    return {"is_beta": u.get("is_beta", False) if u else False}

# ── Moderation API ──
from moderation import get_moderation_stats, check_ban_status

@app.get("/api/moderation/status")
async def moderation_status(request: Request, db=Depends(get_db)):
    """Get moderation status for current user."""
    user = get_current_user(request)
    if not user or user.get("is_guest"):
        return {"violation_score": 0, "warnings": 0, "is_banned": False}
    stats = await get_moderation_stats(db, user["user_id"])
    return stats


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.environ.get("PORT", 8000)), reload=True)
