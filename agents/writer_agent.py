"""
Writer Agent — Reports, essays, summaries, professional writing.
"""
from .base_agent import BaseAgent
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from providers import build_report_prompt, web_search, generate_response


class WriterAgent(BaseAgent):
    def __init__(self):
        super().__init__("WriterAgent", "✍️", "Reports, essays, summaries, professional writing")

    async def run(self, task: str, context: dict) -> dict:
        try:
            api_key  = context.get("api_key", "")
            provider = context.get("provider", "gemini")
            model    = context.get("model", "gemini-2.0-flash")
            research = context.get("research_data", "")

            # Build report prompt with research data
            import re
            topic = task.lower()
            for kw in ["write", "generate", "create", "make", "report on",
                       "essay on", "article on", "summary of", "a report", "an essay"]:
                topic = topic.replace(kw, "").strip()
            topic = re.sub(r"[?.,!\s]+$", "", topic).strip() or task

            prompt = build_report_prompt(topic, research) if research else task

            messages = [{"role": "user", "content": prompt}]
            full = ""
            async for chunk in generate_response(messages, provider, model, api_key, ""):
                full += chunk

            return self.success(full, data={"topic": topic})
        except Exception as e:
            return self.failure(f"Writing failed: {str(e)}")
