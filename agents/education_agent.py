"""
Education Agent — Tutoring, explain concepts, quizzes, study guides.
"""
from .base_agent import BaseAgent
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from providers import generate_response


class EducationAgent(BaseAgent):
    def __init__(self):
        super().__init__("EducationAgent", "📚", "Tutoring, explain concepts, quizzes")

    async def run(self, task: str, context: dict) -> dict:
        try:
            api_key  = context.get("api_key", "")
            provider = context.get("provider", "gemini")
            model    = context.get("model", "gemini-2.0-flash")

            system = "[EDUCATION AGENT] You are an expert tutor. Explain concepts clearly with simple language, real-world examples, and analogies. Break complex topics into easy steps. Use diagrams in text where helpful."
            messages = [{"role": "user", "content": task}]
            full = ""
            async for chunk in generate_response(messages, provider, model, api_key, system):
                full += chunk

            return self.success(full)
        except Exception as e:
            return self.failure(f"Education agent failed: {str(e)}")
