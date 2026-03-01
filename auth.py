"""
Authentication Router
- Google OAuth login
- Email + Password login/signup
- Guest mode
- JWT token management
"""
from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr
from datetime import datetime, timedelta
from typing import Optional
import jwt
import bcrypt
import httpx
import secrets

from config import settings
from database import get_db, get_user_by_email, create_user

router = APIRouter()

# ─── Models ──────────────────────────────────────────────────────

class EmailSignup(BaseModel):
    name: str
    email: EmailStr
    password: str

class EmailLogin(BaseModel):
    email: EmailStr
    password: str

class GoogleToken(BaseModel):
    token: str  # Google ID token

# ─── JWT helpers ─────────────────────────────────────────────────

def create_jwt(user_id: str, email: str, name: str) -> str:
    payload = {
        "user_id": user_id,
        "email": email,
        "name": name,
        "exp": datetime.utcnow() + timedelta(hours=settings.JWT_EXPIRE_HOURS),
        "iat": datetime.utcnow(),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")

def verify_jwt(token: str) -> dict:
    try:
        return jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

def get_current_user(request: Request) -> Optional[dict]:
    """Extract user from Authorization header. Returns None for guest."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    token = auth[7:]
    if token == "guest":
        return {"user_id": "guest", "email": "", "name": "Guest", "is_guest": True}
    try:
        payload = verify_jwt(token)
        payload["is_guest"] = False
        return payload
    except:
        return None

# ─── Routes ──────────────────────────────────────────────────────

@router.post("/signup")
async def signup(data: EmailSignup, db=Depends(get_db)):
    # Check if email exists
    existing = await get_user_by_email(db, data.email)
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    # Hash password
    hashed = bcrypt.hashpw(data.password.encode(), bcrypt.gensalt()).decode()

    # Create user
    user_id = await create_user(db, {
        "name": data.name,
        "email": data.email,
        "password_hash": hashed,
        "photo": f"https://ui-avatars.com/api/?name={data.name}&background=7c3aed&color=fff&bold=true",
        "provider": "email",
        "google_id": None,
    })

    token = create_jwt(user_id, data.email, data.name)
    return {
        "token": token,
        "user": {
            "id": user_id,
            "name": data.name,
            "email": data.email,
            "photo": f"https://ui-avatars.com/api/?name={data.name}&background=7c3aed&color=fff&bold=true"
        }
    }


@router.post("/login")
async def login(data: EmailLogin, db=Depends(get_db)):
    user = await get_user_by_email(db, data.email)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not user.get("password_hash"):
        raise HTTPException(status_code=401, detail="This account uses Google login")

    if not bcrypt.checkpw(data.password.encode(), user["password_hash"].encode()):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    user_id = str(user["_id"])
    token = create_jwt(user_id, user["email"], user["name"])
    return {
        "token": token,
        "user": {
            "id": user_id,
            "name": user["name"],
            "email": user["email"],
            "photo": user.get("photo", "")
        }
    }


@router.post("/google")
async def google_login(data: GoogleToken, db=Depends(get_db)):
    """Verify Google ID token and login/signup user."""
    if not settings.GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=501, detail="Google login not configured")

    # Verify token with Google
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"https://oauth2.googleapis.com/tokeninfo?id_token={data.token}"
        )
        if resp.status_code != 200:
            raise HTTPException(status_code=401, detail="Invalid Google token")
        google_data = resp.json()

    if google_data.get("aud") != settings.GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=401, detail="Token audience mismatch")

    email = google_data["email"]
    name = google_data.get("name", email.split("@")[0])
    photo = google_data.get("picture", "")
    google_id = google_data["sub"]

    # Find or create user
    user = await get_user_by_email(db, email)
    if user:
        user_id = str(user["_id"])
        # Update photo if changed
        await db.users.update_one(
            {"_id": user["_id"]},
            {"$set": {"photo": photo, "google_id": google_id, "updated_at": datetime.utcnow()}}
        )
    else:
        user_id = await create_user(db, {
            "name": name,
            "email": email,
            "password_hash": None,
            "photo": photo,
            "provider": "google",
            "google_id": google_id,
        })

    token = create_jwt(user_id, email, name)
    return {
        "token": token,
        "user": {"id": user_id, "name": name, "email": email, "photo": photo}
    }


@router.get("/guest")
async def guest_login():
    """Generate a guest session (no DB entry)."""
    return {
        "token": "guest",
        "user": {
            "id": "guest",
            "name": "Guest",
            "email": "",
            "photo": "https://ui-avatars.com/api/?name=G&background=334155&color=fff"
        }
    }
