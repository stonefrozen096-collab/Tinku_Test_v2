"""
Research Agent — Web search, fact finding, news, deep research.
Uses ONLY real search results — never makes up information.
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
            from providers import generate_response
            api_key  = context.get("api_key", "")
            provider = context.get("provider", "gemini")
            model    = context.get("model", "gemini-2.0-flash")

            # Get real search results from Tavily/GNews/DuckDuckGo
            result = await web_search(task)
            search_data = result["data"]
            sources = result.get("sources", [])

            # Use AI to summarize ONLY real search data
            if search_data and "No results found" not in search_data:
                system = (
                    "[RESEARCH AGENT] You are a research assistant. "
                    "Summarize the following REAL search results accurately. "
                    "ONLY use information from the search results provided. "
                    "NEVER make up or add information not in the results. "
                    "If the results mention specific news — report them accurately. "
                    "Present findings clearly with dates and sources where available."
                )
                prompt = f"Question: {task}\n\nReal Search Results:\n{search_data}\n\nProvide an accurate summary based ONLY on the above real search results. Do not add any information not present in the results."
                messages = [{"role": "user", "content": prompt}]
                full = ""
                async for chunk in generate_response(messages, provider, model, api_key, system):
                    full += chunk
                return self.success(full, data={"query": task, "raw": search_data}, sources=sources)
            else:
                return self.success(search_data, data={"query": task}, sources=sources)

        except Exception as e:
            return self.failure(f"Research failed: {str(e)}")
