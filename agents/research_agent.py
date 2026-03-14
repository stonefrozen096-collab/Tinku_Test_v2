"""
Research Agent — Web search, fact finding, news, deep research.
"""
from .base_agent import BaseAgent
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from providers import web_search


class ResearchAgent(BaseAgent):
    def __init__(self):
        super().__init__("ResearchAgent", "🔬", "Web search, fact finding, news research")

    async def run(self, task: str, context: dict) -> dict:
        try:
            result = await web_search(task)
            return self.success(
                result["data"],
                data={"query": task},
                sources=result.get("sources", [])
            )
        except Exception as e:
            return self.failure(f"Research failed: {str(e)}")
