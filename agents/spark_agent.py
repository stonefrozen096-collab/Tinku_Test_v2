"""
Tinku Spark Agent — Personalized idea generation engine.
Uses TME (Tinku Memory Engine) to generate ideas tailored to the user.
"""
from .base_agent import BaseAgent
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from providers import generate_response


class SparkAgent(BaseAgent):
    def __init__(self):
        super().__init__("SparkAgent", "⚡", "Personalized idea generation")

    async def run(self, task: str, context: dict) -> dict:
        try:
            api_key  = context.get("api_key", "")
            provider = context.get("provider", "gemini")
            model    = context.get("model", "gemini-2.0-flash")
            memory   = context.get("memory", "")

            system = (
                "[TINKU SPARK] You are Tinku's idea generation engine. "
                "Generate creative, actionable, personalized ideas based on "
                "the user's profile and request. "
                "Use their memory context to make ideas highly relevant. "
                "Format ideas clearly with: title, description, why it fits them, "
                "and first step to start. Make ideas specific to India market if relevant."
            )

            memory_context = f"\n\nUser Profile:\n{memory}" if memory else ""
            prompt = f"{task}{memory_context}\n\nGenerate 5 personalized, actionable ideas."
            messages = [{"role": "user", "content": prompt}]

            full = ""
            async for chunk in generate_response(messages, provider, model, api_key, system):
                full += chunk

            return self.success(full)
        except Exception as e:
            return self.failure(f"Spark failed: {str(e)}")
