"""
Creative Agent — Stories, poems, creative writing, brainstorming.
"""
from .base_agent import BaseAgent
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from providers import generate_response


class CreativeAgent(BaseAgent):
    def __init__(self):
        super().__init__("CreativeAgent", "🎨", "Stories, poems, creative writing")

    async def run(self, task: str, context: dict) -> dict:
        try:
            api_key  = context.get("api_key", "")
            provider = context.get("provider", "gemini")
            model    = context.get("model", "gemini-2.0-flash")

            system = "[CREATIVE AGENT] You are a creative writer with exceptional imagination. Write vivid, engaging, emotionally resonant content. Use rich descriptions, metaphors, and narrative flow."
            messages = [{"role": "user", "content": task}]
            full = ""
            async for chunk in generate_response(messages, provider, model, api_key, system):
                full += chunk

            return self.success(full)
        except Exception as e:
            return self.failure(f"Creative agent failed: {str(e)}")
