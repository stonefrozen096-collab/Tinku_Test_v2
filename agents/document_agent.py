"""
Document Agent — Summarize, extract data, convert documents.
"""
from .base_agent import BaseAgent
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from providers import analyze_file, generate_response


class DocumentAgent(BaseAgent):
    def __init__(self):
        super().__init__("DocumentAgent", "📄", "Summarize, extract, convert documents")

    async def run(self, task: str, context: dict) -> dict:
        try:
            api_key     = context.get("api_key", "")
            provider    = context.get("provider", "gemini")
            model       = context.get("model", "gemini-2.0-flash")
            file_content = context.get("file_content", "")
            file_name   = context.get("file_name", "document")

            if file_content:
                result = await analyze_file(file_content, file_name)
                context_str = f"\n\n[DOCUMENT CONTENT]\n{result['data']}"
            else:
                context_str = ""

            system = "[DOCUMENT AGENT] You are an expert at analyzing documents. Summarize clearly, extract key information, identify important data points, and present findings in a structured format."
            messages = [{"role": "user", "content": task + context_str}]
            full = ""
            async for chunk in generate_response(messages, provider, model, api_key, system):
                full += chunk

            return self.success(full)
        except Exception as e:
            return self.failure(f"Document agent failed: {str(e)}")
