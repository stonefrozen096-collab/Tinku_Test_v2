"""
Conversation Agent — Handles chat flow, follow-ups, conversation context.
"""
import re
from .base_agent import BaseAgent
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from providers import generate_response


class ConversationAgent(BaseAgent):
    def __init__(self):
        super().__init__("ConversationAgent", "💬", "Chat flow, follow-ups, context understanding")

    def resolve_references(self, task: str, history: list) -> str:
        """Resolve pronouns and references like 'it', 'that', 'the previous one'."""
        if not history:
            return task

        # Find last topic from history
        last_assistant = ""
        last_user = ""
        for msg in reversed(history):
            if msg.get("role") == "assistant" and not last_assistant:
                last_assistant = msg.get("content", "")[:200]
            if msg.get("role") == "user" and not last_user:
                last_user = msg.get("content", "")
            if last_assistant and last_user:
                break

        # Add context for ambiguous references
        ambiguous = ["it", "that", "this", "the previous", "same", "update it",
                     "change it", "fix it", "improve it"]
        task_lower = task.lower()

        if any(ref in task_lower for ref in ambiguous) and last_user:
            return f"{task}\n[Context: Previous topic was: {last_user[:100]}]"

        return task

    async def run(self, task: str, context: dict) -> dict:
        try:
            api_key  = context.get("api_key", "")
            provider = context.get("provider", "gemini")
            model    = context.get("model", "gemini-2.0-flash")
            history  = context.get("history", [])

            resolved_task = self.resolve_references(task, history)

            system = "[CONVERSATION AGENT] You are a friendly, context-aware conversational AI. Maintain conversation flow naturally, remember what was discussed, handle follow-up questions gracefully."
            messages = history + [{"role": "user", "content": resolved_task}]
            full = ""
            async for chunk in generate_response(messages, provider, model, api_key, system):
                full += chunk

            return self.success(full)
        except Exception as e:
            return self.failure(f"Conversation agent failed: {str(e)}")
