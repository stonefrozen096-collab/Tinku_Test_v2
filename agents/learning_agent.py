"""
Learning Agent — Learns user preferences over time.
Tracks preferred tone, response length, writing style.
"""
from .base_agent import BaseAgent
from datetime import datetime


class LearningAgent(BaseAgent):
    def __init__(self):
        super().__init__("LearningAgent", "🤖", "Learns and adapts to user preferences")

    async def learn(self, db, user_id: str, message: str, response: str):
        """Extract and save user preferences from interaction."""
        if not db or user_id == "guest":
            return

        prefs = {}

        # Detect preferred response length
        msg_lower = message.lower()
        if any(w in msg_lower for w in ["brief", "short", "quick", "summarize", "tldr"]):
            prefs["response_length"] = "short"
        elif any(w in msg_lower for w in ["detailed", "explain fully", "in depth", "comprehensive"]):
            prefs["response_length"] = "detailed"

        # Detect preferred tone
        if any(w in msg_lower for w in ["formal", "professional", "official"]):
            prefs["tone"] = "formal"
        elif any(w in msg_lower for w in ["casual", "simple", "easy", "friendly"]):
            prefs["tone"] = "casual"

        # Detect language preference
        if any(w in msg_lower for w in ["in hindi", "hindi mein", "हिंदी"]):
            prefs["language"] = "hindi"
        elif any(w in msg_lower for w in ["in tamil", "தமிழில்"]):
            prefs["language"] = "tamil"

        if prefs:
            for key, value in prefs.items():
                await db.user_preferences.update_one(
                    {"user_id": user_id, "key": key},
                    {"$set": {
                        "user_id":    user_id,
                        "key":        key,
                        "value":      value,
                        "updated_at": datetime.utcnow()
                    }},
                    upsert=True
                )

    async def get_preferences(self, db, user_id: str) -> dict:
        """Get learned preferences for a user."""
        if not db or user_id == "guest":
            return {}
        prefs = {}
        async for item in db.user_preferences.find({"user_id": user_id}):
            prefs[item["key"]] = item["value"]
        return prefs

    async def build_preference_instruction(self, db, user_id: str) -> str:
        """Build instruction string from learned preferences."""
        prefs = await self.get_preferences(db, user_id)
        if not prefs:
            return ""

        instructions = []
        if prefs.get("response_length") == "short":
            instructions.append("Keep responses brief and concise.")
        elif prefs.get("response_length") == "detailed":
            instructions.append("Provide detailed, comprehensive responses.")
        if prefs.get("tone") == "formal":
            instructions.append("Use formal, professional language.")
        elif prefs.get("tone") == "casual":
            instructions.append("Use casual, friendly language.")
        if prefs.get("language"):
            instructions.append(f"Respond in {prefs['language']} when appropriate.")

        return " ".join(instructions)

    async def run(self, task: str, context: dict) -> dict:
        try:
            db       = context.get("db")
            user_id  = context.get("user_id", "guest")
            response = context.get("response", "")

            await self.learn(db, user_id, task, response)
            instruction = await self.build_preference_instruction(db, user_id)

            return self.success(
                "Preferences updated",
                data={"instruction": instruction}
            )
        except Exception as e:
            return self.failure(f"Learning agent failed: {str(e)}")
