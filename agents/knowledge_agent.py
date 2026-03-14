"""
Knowledge Base Agent — Stores and retrieves user documents, notes, FAQs.
"""
from .base_agent import BaseAgent
from datetime import datetime
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from providers import generate_response


class KnowledgeAgent(BaseAgent):
    def __init__(self):
        super().__init__("KnowledgeAgent", "🧠", "Store and retrieve knowledge, notes, documents")

    async def save_knowledge(self, db, user_id: str, title: str, content: str):
        """Save a knowledge item to MongoDB."""
        await db.knowledge_base.update_one(
            {"user_id": user_id, "title": title},
            {"$set": {
                "user_id": user_id,
                "title": title,
                "content": content[:5000],
                "updated_at": datetime.utcnow()
            }},
            upsert=True
        )

    async def search_knowledge(self, db, user_id: str, query: str) -> list:
        """Search knowledge base for relevant items."""
        results = []
        query_lower = query.lower()
        async for item in db.knowledge_base.find({"user_id": user_id}):
            if any(word in item.get("content", "").lower() for word in query_lower.split()):
                results.append(item)
        return results[:3]

    async def run(self, task: str, context: dict) -> dict:
        try:
            api_key  = context.get("api_key", "")
            provider = context.get("provider", "gemini")
            model    = context.get("model", "gemini-2.0-flash")
            db       = context.get("db")
            user_id  = context.get("user_id", "guest")
            task_lower = task.lower()

            knowledge_context = ""

            # Search existing knowledge
            if db and user_id != "guest":
                items = await self.search_knowledge(db, user_id, task)
                if items:
                    knowledge_context = "\n\n[YOUR KNOWLEDGE BASE]\n"
                    for item in items:
                        knowledge_context += f"- {item['title']}: {item['content'][:300]}\n"

            system = "[KNOWLEDGE AGENT] You help users store and retrieve their personal knowledge base. When asked to save, confirm what was saved. When asked to recall, retrieve relevant information clearly."
            messages = [{"role": "user", "content": task + knowledge_context}]
            full = ""
            async for chunk in generate_response(messages, provider, model, api_key, system):
                full += chunk

            return self.success(full)
        except Exception as e:
            return self.failure(f"Knowledge agent failed: {str(e)}")
