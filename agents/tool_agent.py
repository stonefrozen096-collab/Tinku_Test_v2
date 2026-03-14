"""
Tool Agent — Handles all external tool operations:
APIs, databases, file operations, PDF/Word/Zip creation.
"""
from .base_agent import BaseAgent
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from providers import fetch_url_content, get_exchange_rate


class ToolAgent(BaseAgent):
    def __init__(self):
        super().__init__("ToolAgent", "🔧", "External tools, APIs, file operations")

    async def run(self, task: str, context: dict) -> dict:
        try:
            task_lower = task.lower()
            results = []
            sources = []

            # URL fetching
            url = context.get("url_value", "")
            if url:
                result = await fetch_url_content(url)
                results.append(f"[URL Content]\n{result['data']}")
                sources.extend(result.get("sources", []))

            # Currency/exchange
            if any(w in task_lower for w in ["exchange", "currency", "convert", "usd", "inr"]):
                result = await get_exchange_rate()
                results.append(f"[Exchange Rates]\n{result['data']}")
                sources.extend(result.get("sources", []))

            # File export request
            if any(w in task_lower for w in ["pdf", "word", "docx", "export", "download", "zip"]):
                fmt = "pdf" if "pdf" in task_lower else "docx"
                results.append(f"[EXPORT_REQUEST: {fmt}]")

            combined = "\n\n".join(results) if results else "No tool operation needed"
            return self.success(combined, sources=sources)

        except Exception as e:
            return self.failure(f"Tool agent failed: {str(e)}")
