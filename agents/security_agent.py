"""
Security Agent — Detects unsafe prompts, API key exposure, prompt injection.
Runs BEFORE any other agent.
"""
import re
from .base_agent import BaseAgent


UNSAFE_PATTERNS = [
    r"ignore (all )?previous instructions",
    r"forget (all )?previous",
    r"you are now",
    r"pretend (you are|to be)",
    r"act as (a |an )?(?!tinku)",
    r"jailbreak",
    r"dan mode",
    r"developer mode",
    r"bypass (safety|filter|restriction)",
    r"(bomb|weapon|explosive|poison|hack|malware|virus).*(make|create|build|how to)",
]

API_KEY_PATTERNS = [
    r"sk-[a-zA-Z0-9]{20,}",           # OpenAI
    r"AIza[0-9A-Za-z\-_]{35}",        # Google
    r"gsk_[a-zA-Z0-9]{50,}",          # Groq
    r"[a-f0-9]{32,}",                  # Generic API keys
]

SENSITIVE_PATTERNS = [
    r"\b\d{16}\b",                     # Credit card
    r"\b\d{3}-\d{2}-\d{4}\b",        # SSN
    r"password\s*[:=]\s*\S+",         # Password
]


class SecurityAgent(BaseAgent):
    def __init__(self):
        super().__init__("SecurityAgent", "🔒", "Detects unsafe prompts and sensitive data")

    async def run(self, task: str, context: dict) -> dict:
        msg = task.lower()
        warnings = []

        # Check prompt injection
        for pattern in UNSAFE_PATTERNS:
            if re.search(pattern, msg, re.IGNORECASE):
                return self.failure(f"⚠️ Unsafe prompt detected. I can't help with that.")

        # Check API key exposure
        for pattern in API_KEY_PATTERNS:
            if re.search(pattern, task):
                warnings.append("⚠️ Possible API key detected in message — removed for safety.")
                task = re.sub(pattern, "[REDACTED]", task)

        # Check sensitive data
        for pattern in SENSITIVE_PATTERNS:
            if re.search(pattern, task, re.IGNORECASE):
                warnings.append("⚠️ Sensitive data detected — please avoid sharing personal info.")

        return self.success(
            "Security check passed",
            data={"clean_message": task, "warnings": warnings}
        )
