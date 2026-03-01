"""
MongoDB connection and collections using Motor (async MongoDB driver)
"""
from motor.motor_asyncio import AsyncIOMotorClient
from config import settings
from datetime import datetime


class DBClient:
    def __init__(self):
        self.client = None
        self.db = None

    async def connect(self):
        self.client = AsyncIOMotorClient(settings.MONGODB_URL)
        self.db = self.client[settings.MONGODB_DB]
        # Create indexes
        await self._create_indexes()

    async def disconnect(self):
        if self.client:
            self.client.close()

    async def _create_indexes(self):
        # Users
        await self.db.users.create_index("email", unique=True)
        await self.db.users.create_index("google_id", sparse=True)
        # Conversations
        await self.db.conversations.create_index("user_id")
        await self.db.conversations.create_index("created_at")
        # Messages
        await self.db.messages.create_index("conversation_id")
        await self.db.messages.create_index("flagged")
        # Stats
        await self.db.stats.create_index("user_id", unique=True)


db_client = DBClient()


def get_db():
    return db_client.db


# ─── Helper functions ───────────────────────────────────────────

async def get_user_by_email(db, email: str):
    return await db.users.find_one({"email": email})

async def get_user_by_id(db, user_id: str):
    from bson import ObjectId
    return await db.users.find_one({"_id": ObjectId(user_id)})

async def create_user(db, user_data: dict):
    user_data["created_at"] = datetime.utcnow()
    user_data["updated_at"] = datetime.utcnow()
    user_data["is_active"] = True
    result = await db.users.insert_one(user_data)
    return str(result.inserted_id)

async def save_conversation(db, user_id: str, title: str, model: str, provider: str):
    conv = {
        "user_id": user_id,
        "title": title,
        "model": model,
        "provider": provider,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
        "message_count": 0,
    }
    result = await db.conversations.insert_one(conv)
    return str(result.inserted_id)

async def save_message(db, conv_id: str, user_id: str, role: str, content: str,
                       tools_used: list = None, flagged: bool = False, flag_reason: str = ""):
    msg = {
        "conversation_id": conv_id,
        "user_id": user_id,
        "role": role,
        "content": content,
        "tools_used": tools_used or [],
        "flagged": flagged,
        "flag_reason": flag_reason,
        "created_at": datetime.utcnow(),
    }
    result = await db.messages.insert_one(msg)
    # Update conversation message count
    from bson import ObjectId
    await db.conversations.update_one(
        {"_id": ObjectId(conv_id)},
        {"$inc": {"message_count": 1}, "$set": {"updated_at": datetime.utcnow()}}
    )
    return str(result.inserted_id)

async def update_user_stats(db, user_id: str, provider: str, model: str):
    """Update usage statistics for a user."""
    today = datetime.utcnow().strftime("%Y-%m-%d")
    await db.stats.update_one(
        {"user_id": user_id},
        {
            "$inc": {
                "total_messages": 1,
                f"messages_by_provider.{provider}": 1,
                f"messages_by_model.{model}": 1,
                f"daily.{today}": 1,
            },
            "$set": {"last_active": datetime.utcnow()},
            "$setOnInsert": {"user_id": user_id, "created_at": datetime.utcnow()}
        },
        upsert=True
    )

async def flag_message(db, message_id: str, reason: str):
    """Flag an inappropriate message."""
    from bson import ObjectId
    await db.messages.update_one(
        {"_id": ObjectId(message_id)},
        {"$set": {"flagged": True, "flag_reason": reason, "flagged_at": datetime.utcnow()}}
    )
