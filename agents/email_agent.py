"""
Email Agent — Draft professional emails, replies, follow-ups.
"""
from .base_agent import BaseAgent
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from providers import generate_response


class EmailAgent(BaseAgent):
    def __init__(self):
        super().__init__("EmailAgent", "📧", "Draft professional emails and replies")

    async def run(self, task: str, context: dict) -> dict:
        try:
            api_key  = context.get("api_key", "")
            provider = context.get("provider", "gemini")
            model    = context.get("model", "gemini-2.0-flash")

            system = "[EMAIL AGENT] You are an expert at writing professional emails. Always include: Subject line, greeting, clear body, call to action, and professional sign-off. Match the tone to the context (formal/informal)."
            messages = [{"role": "user", "content": task}]
            full = ""
            async for chunk in generate_response(messages, provider, model, api_key, system):
                full += chunk

            return self.success(full)
        except Exception as e:
            return self.failure(f"Email agent failed: {str(e)}")
