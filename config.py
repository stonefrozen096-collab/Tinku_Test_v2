"""
Tinku v2 — Configuration
All settings come from environment variables (set in Render dashboard)
"""
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # MongoDB
    MONGODB_URL: str = "mongodb://localhost:27017"
    MONGODB_DB: str = "tinku_db"

    # AI Providers (set whichever you have)
    GEMINI_API_KEY: Optional[str] = None
    GROQ_API_KEY: Optional[str] = None
    ANTHROPIC_API_KEY: Optional[str] = None

    # Google OAuth
    GOOGLE_CLIENT_ID: Optional[str] = None
    GOOGLE_CLIENT_SECRET: Optional[str] = None

    # JWT Secret (for session tokens)
    JWT_SECRET: str = "change-this-to-a-random-secret-key-in-production"
    JWT_EXPIRE_HOURS: int = 168  # 7 days

    # App
    APP_NAME: str = "Tinku"
    APP_URL: str = "http://localhost:8000"
    DEBUG: bool = False

    # Content moderation
    ENABLE_CONTENT_FLAGGING: bool = True

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
