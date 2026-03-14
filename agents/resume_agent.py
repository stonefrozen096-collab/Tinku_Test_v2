"""
Resume Agent — Build, analyze, update professional resumes.
"""
from .base_agent import BaseAgent
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from providers import generate_response


class ResumeAgent(BaseAgent):
    def __init__(self):
        super().__init__("ResumeAgent", "📋", "Build, analyze and update professional resumes")

    async def run(self, task: str, context: dict) -> dict:
        try:
            api_key  = context.get("api_key", "")
            provider = context.get("provider", "gemini")
            model    = context.get("model", "gemini-2.0-flash")
            resume_data = context.get("resume_data", {})

            system = "[RESUME AGENT] You are an expert resume writer and career coach. Build ATS-friendly resumes with strong action verbs, quantified achievements, and clear formatting. Tailor content for the target role."

            # Include existing resume data if available
            extra = ""
            if resume_data:
                extra = f"\n\nExisting resume data: {resume_data}"

            messages = [{"role": "user", "content": task + extra}]
            full = ""
            async for chunk in generate_response(messages, provider, model, api_key, system):
                full += chunk

            return self.success(full)
        except Exception as e:
            return self.failure(f"Resume agent failed: {str(e)}")
