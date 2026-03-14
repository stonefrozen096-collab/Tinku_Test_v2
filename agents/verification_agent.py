"""
Verification Agent — Checks responses for accuracy, completeness, mistakes.
Runs AFTER other agents, BEFORE sending to user.
"""
from .base_agent import BaseAgent
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from providers import generate_response


class VerificationAgent(BaseAgent):
    def __init__(self):
        super().__init__("VerificationAgent", "✅", "Verifies accuracy and quality of responses")

    async def run(self, task: str, context: dict) -> dict:
        try:
            api_key   = context.get("api_key", "")
            provider  = context.get("provider", "gemini")
            model     = context.get("model", "gemini-2.0-flash")
            response  = context.get("response_to_verify", "")
            original  = context.get("original_question", task)

            if not response or len(response) < 50:
                return self.success(response)

            verify_prompt = f"""You are a quality checker. Review this AI response and check:
1. Does it fully answer the question?
2. Are there any obvious errors or hallucinations?
3. Is it complete or cut off?
4. Is the information accurate?

Original question: {original}

Response to verify:
{response[:2000]}

If the response is good, reply with just: [VERIFIED]
If it needs improvement, reply with the improved version directly."""

            messages = [{"role": "user", "content": verify_prompt}]
            verified = ""
            async for chunk in generate_response(messages, provider, model, api_key, ""):
                verified += chunk

            # If verified, return original. If improved, return improved version.
            final = response if "[VERIFIED]" in verified else verified
            return self.success(final, data={"was_improved": "[VERIFIED]" not in verified})

        except Exception as e:
            # If verification fails, just return original response
            return self.success(context.get("response_to_verify", task))
