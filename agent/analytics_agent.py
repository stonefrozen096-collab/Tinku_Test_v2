"""
Analytics Agent — Tracks usage, feature popularity, response times.
Stores data in MongoDB for dashboard display.
"""
from .base_agent import BaseAgent
from datetime import datetime


class AnalyticsAgent(BaseAgent):
    def __init__(self):
        super().__init__("AnalyticsAgent", "📈", "Tracks usage and feature analytics")

    async def track(self, db, user_id: str, agents_used: list, message: str):
        """Save analytics event to MongoDB."""
        if not db or user_id == "guest":
            return
        try:
            await db.analytics.insert_one({
                "user_id":     user_id,
                "agents_used": agents_used,
                "message_len": len(message),
                "timestamp":   datetime.utcnow(),
                "date":        datetime.utcnow().strftime("%Y-%m-%d")
            })
            # Update feature counters
            for agent in agents_used:
                await db.analytics_summary.update_one(
                    {"user_id": user_id, "agent": agent},
                    {"$inc": {"count": 1}, "$set": {"last_used": datetime.utcnow()}},
                    upsert=True
                )
        except Exception:
            pass

    async def get_summary(self, db, user_id: str) -> dict:
        """Get analytics summary for a user."""
        if not db or user_id == "guest":
            return {}
        try:
            summary = {}
            async for item in db.analytics_summary.find({"user_id": user_id}):
                summary[item["agent"]] = item["count"]
            total = await db.analytics.count_documents({"user_id": user_id})
            return {"feature_counts": summary, "total_messages": total}
        except Exception:
            return {}

    async def run(self, task: str, context: dict) -> dict:
        try:
            db          = context.get("db")
            user_id     = context.get("user_id", "guest")
            agents_used = context.get("completed_agents", [])

            await self.track(db, user_id, agents_used, task)
            summary = await self.get_summary(db, user_id)

            return self.success(
                "Analytics tracked",
                data=summary
            )
        except Exception as e:
            return self.failure(f"Analytics agent failed: {str(e)}")
