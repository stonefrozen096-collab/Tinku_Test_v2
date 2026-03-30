"""
Tinku AI — Phase 9: Long Term Memory
Uses MongoDB to store and retrieve user memories across conversations.
"""
import re
from datetime import datetime
from typing import Optional


# ════════════════════════════════════════
# FACT EXTRACTION
# Detects important facts from user messages
# ════════════════════════════════════════

MEMORY_PATTERNS = [
    # Name — strict patterns only, "i am X" removed (too broad)
    (r"my name is ([A-Za-z]+(?: [A-Za-z]+)*)", "name"),
    (r"call me ([A-Za-z]+(?: [A-Za-z]+)*)", "name"),
    (r"people call me ([A-Za-z]+(?: [A-Za-z]+)*)", "name"),

    # Age
    (r"i(?:'m| am) (\d{1,2}) years old", "age"),
    (r"my age is (\d{1,2})", "age"),

    # Location
    (r"i live in ([A-Za-z ]+?)(?:\.|,|$)", "location"),
    (r"i(?:'m| am) based in ([A-Za-z ]+?)(?:\.|,|$)", "location"),
    (r"my city is ([A-Za-z ]+?)(?:\.|,|$)", "location"),
    (r"i(?:'m| am) from ([A-Za-z]+(?:\s[A-Za-z]+){0,2})(?:\.|,|$)", "location"),

    # Profession — only explicit job statements
    (r"i(?:'m| am) (?:a |an )(developer|engineer|designer|student|teacher|doctor|manager|analyst|scientist|architect|writer|artist)", "profession"),
    (r"i work as (?:a |an )?([a-z ]+?)(?:\.|,|$)", "profession"),
    (r"i(?:'m| am) studying ([a-z ]+?)(?:\.|,|$)", "profession"),
    (r"my profession is ([a-z ]+?)(?:\.|,|$)", "profession"),

    # Interests — only when followed by noun, not verb
    (r"my hobby is ([a-z ]+?)(?:\.|,|$)", "interest"),
    (r"i(?:'m| am) interested in ([a-z ]+?)(?:\.|,|$)", "interest"),
    (r"i love ([a-z ]+?)(?:\.|,|$)", "interest"),
    (r"my favourite is ([a-z ]+?)(?:\.|,|$)", "interest"),

    # Language
    (r"i speak ([a-z]+)", "language"),
    (r"my language is ([a-z]+)", "language"),

    # Project
    (r"i(?:'m| am) working on ([a-zA-Z0-9 ]+?)(?:\.|,|$)", "project"),
    (r"my project is ([a-zA-Z0-9 ]+?)(?:\.|,|$)", "project"),
    (r"i(?:'m| am) building ([a-zA-Z0-9 ]+?)(?:\.|,|$)", "project"),
]


def extract_facts(message: str) -> dict:
    """Extract key facts from a user message."""
    facts = {}
    msg_lower = message.lower()

    for pattern, key in MEMORY_PATTERNS:
        match = re.search(pattern, msg_lower, re.IGNORECASE)
        if match:
            value = match.group(1).strip().rstrip(".,!?")
            # Skip very short or very long values
            if 2 <= len(value) <= 50:
                facts[key] = value

    return facts


# ════════════════════════════════════════
# MEMORY OPERATIONS
# Save, retrieve, format memories from MongoDB
# ════════════════════════════════════════

async def save_memory(db, user_id: str, facts: dict):
    """Save extracted facts to user memory in MongoDB."""
    if not facts or user_id == "guest":
        return

    now = datetime.utcnow()

    for key, value in facts.items():
        await db.memories.update_one(
            {"user_id": user_id, "key": key},
            {"$set": {
                "user_id": user_id,
                "key": key,
                "value": value,
                "updated_at": now
            }},
            upsert=True
        )


async def get_memories(db, user_id: str) -> dict:
    """Retrieve all memories for a user."""
    if user_id == "guest":
        return {}

    memories = {}
    async for mem in db.memories.find({"user_id": user_id}):
        memories[mem["key"]] = mem["value"]

    return memories


async def save_topic(db, user_id: str, topic: str):
    """Save a topic the user discussed for context."""
    if user_id == "guest" or not topic:
        return

    await db.memory_topics.update_one(
        {"user_id": user_id, "topic": topic[:100]},
        {"$set": {
            "user_id": user_id,
            "topic": topic[:100],
            "updated_at": datetime.utcnow()
        },
        "$inc": {"count": 1}},
        upsert=True
    )


async def get_recent_topics(db, user_id: str, limit: int = 5) -> list:
    """Get recently discussed topics."""
    if user_id == "guest":
        return []

    topics = []
    cursor = db.memory_topics.find(
        {"user_id": user_id}
    ).sort("updated_at", -1).limit(limit)

    async for t in cursor:
        topics.append(t["topic"])

    return topics


def format_memory_context(memories: dict, recent_topics: list) -> str:
    """Format memories into a clean context string for the AI."""
    if not memories and not recent_topics:
        return ""

    parts = []

    if memories.get("name"):
        parts.append(f"User's name: {memories['name']}")
    if memories.get("age"):
        parts.append(f"Age: {memories['age']}")
    if memories.get("location"):
        parts.append(f"Location: {memories['location']}")
    if memories.get("profession"):
        parts.append(f"Profession: {memories['profession']}")
    if memories.get("project"):
        parts.append(f"Current project: {memories['project']}")
    if memories.get("interest"):
        parts.append(f"Interests: {memories['interest']}")
    if memories.get("language"):
        parts.append(f"Language: {memories['language']}")

    if recent_topics:
        parts.append(f"Recently discussed: {', '.join(recent_topics)}")

    return "\n".join(parts) if parts else ""


async def get_memory_summary(db, user_id: str) -> dict:
    """Get full memory summary for display in UI."""
    memories = await get_memories(db, user_id)
    recent_topics = await get_recent_topics(db, user_id, limit=10)
    return {
        "memories": memories,
        "recent_topics": recent_topics,
        "total": len(memories) + len(recent_topics)
    }
