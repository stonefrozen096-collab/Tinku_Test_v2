"""
Code Agent — Write, debug, explain, execute code.
"""
from .base_agent import BaseAgent
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from providers import execute_code, extract_code_from_message, generate_response


class CodeAgent(BaseAgent):
    def __init__(self):
        super().__init__("CodeAgent", "💻", "Write, debug, explain and execute code")

    async def run(self, task: str, context: dict) -> dict:
        try:
            api_key  = context.get("api_key", "")
            provider = context.get("provider", "gemini")
            model    = context.get("model", "gemini-2.0-flash")

            # Check if there's code to execute
            code = extract_code_from_message(task)
            exec_output = ""
            if code:
                exec_result = await execute_code(code)
                exec_output = f"\n\n[CODE OUTPUT]\n{exec_result['data']}"

            # Generate code response
            system = "[CODE AGENT] You are an expert programmer. Write clean, well-commented code. If asked to debug, explain the issue clearly. Always provide working examples."
            messages = [{"role": "user", "content": task + exec_output}]
            full = ""
            async for chunk in generate_response(messages, provider, model, api_key, system):
                full += chunk

            return self.success(full, data={"had_code": bool(code)})
        except Exception as e:
            return self.failure(f"Code agent failed: {str(e)}")
