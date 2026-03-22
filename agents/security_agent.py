"""
Security Agent — Detects unsafe prompts, API key exposure,
prompt injection, and malicious code patterns.
Runs BEFORE any other agent.
"""
import re
from .base_agent import BaseAgent


# ── Prompt Injection Patterns ──
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

# ── API Key Patterns ──
API_KEY_PATTERNS = [
    r"sk-[a-zA-Z0-9]{20,}",           # OpenAI
    r"AIza[0-9A-Za-z\-_]{35}",        # Google
    r"gsk_[a-zA-Z0-9]{50,}",          # Groq
    r"[a-f0-9]{32,}",                  # Generic
]

# ── Sensitive Data Patterns ──
SENSITIVE_PATTERNS = [
    r"\b\d{16}\b",                     # Credit card
    r"\b\d{3}-\d{2}-\d{4}\b",        # SSN
    r"password\s*[:=]\s*\S+",         # Password
]

# ── Dangerous Code Imports ──
DANGEROUS_IMPORTS = [
    "subprocess", "ctypes", "mmap", "ptrace",
    "pty", "pexpect", "fabric", "paramiko",
    "socket", "asyncio.subprocess",
]

# ── Dangerous Code Patterns ──
MALICIOUS_CODE_PATTERNS = [
    # File system attacks
    r"os\.system\s*\(",
    r"os\.popen\s*\(",
    r"os\.remove\s*\(",
    r"os\.unlink\s*\(",
    r"os\.rmdir\s*\(",
    r"shutil\.rmtree\s*\(",
    r"open\s*\(['\"]\/",              # Open files from root
    r"rm\s+-rf",                       # Shell rm command

    # Environment variable theft
    r"os\.environ(?!\[.KEY.\])",       # Print all env vars
    r"os\.getenv\s*\(\s*['\"](?:MONGODB|GROQ|GEMINI|CLAUDE|JWT|SECRET|API_KEY)",

    # Code execution
    r"eval\s*\(",
    r"exec\s*\(",
    r"compile\s*\(",
    r"__import__\s*\(",

    # Network attacks
    r"urllib\.request\.urlretrieve",
    r"while\s+True\s*:\s*(?:pass|requests\.get)",  # DDoS loop

    # Memory/CPU bombs
    r"while\s+True\s*:\s*\n?\s*(?:pass|x\.append|fork)",
    r"os\.fork\s*\(",

    # Pickle attacks
    r"pickle\.loads\s*\(",
    r"pickle\.load\s*\(",

    # Subprocess
    r"subprocess\.(run|call|Popen|check_output)\s*\(",
]

# ── Safe Imports Whitelist ──
SAFE_IMPORTS = {
    "math", "random", "datetime", "json", "re",
    "string", "collections", "itertools", "functools",
    "typing", "dataclasses", "enum", "abc",
    "time", "calendar", "decimal", "fractions",
    "statistics", "heapq", "bisect", "array",
    "copy", "pprint", "textwrap", "unicodedata",
    "hashlib", "hmac", "secrets",
    "base64", "binascii", "struct",
    "io", "pathlib",
    "numpy", "pandas", "matplotlib",
    "requests", "httpx", "aiohttp",
    "flask", "fastapi", "django",
    "sqlalchemy", "pymongo", "redis",
    "PIL", "cv2", "sklearn",
    "torch", "tensorflow", "keras",
}


class SecurityAgent(BaseAgent):
    def __init__(self):
        super().__init__("SecurityAgent", "🔒", "Detects unsafe prompts, malicious code and sensitive data")

    def check_malicious_code(self, message: str) -> list:
        """Check for malicious code patterns in message."""
        threats = []

        # Check dangerous imports
        import_matches = re.findall(r"import\s+(\w+)", message, re.IGNORECASE)
        from_matches = re.findall(r"from\s+(\w+)\s+import", message, re.IGNORECASE)
        all_imports = set(import_matches + from_matches)

        for imp in all_imports:
            if imp in DANGEROUS_IMPORTS:
                threats.append(f"Dangerous import detected: {imp}")

        # Check malicious patterns
        for pattern in MALICIOUS_CODE_PATTERNS:
            if re.search(pattern, message, re.IGNORECASE):
                threats.append(f"Malicious code pattern detected")
                break

        return threats

    async def run(self, task: str, context: dict) -> dict:
        msg = task.lower()
        warnings = []
        clean_message = task

        # ── Check prompt injection ──
        for pattern in UNSAFE_PATTERNS:
            if re.search(pattern, msg, re.IGNORECASE):
                return self.failure(
                    "⚠️ Unsafe prompt detected. I can't help with that.",
                )

        # ── Check malicious code in message ──
        code_threats = self.check_malicious_code(task)
        if code_threats:
            return self.failure(
                "🛡️ Tinku Shield detected potentially harmful code patterns. "
                "For security reasons, I cannot execute or assist with this code. "
                "Please remove system calls, file operations, or dangerous imports.",
            )

        # ── Block requests to WRITE dangerous code ──
        task_lower = task.lower()
        dangerous_write_patterns = [
            (r"(write|create|show|give|generate|make).*(subprocess)", "subprocess"),
            (r"(write|create|show|give|generate|make).*(os\.system)", "os.system"),
            (r"(write|create|show|give|generate|make).*(os\.environ)", "os.environ"),
            (r"(write|create|show|give|generate|make).*(eval|exec)\s*\(", "eval/exec"),
            (r"(write|create|show|give|generate|make).*(pickle\.loads)", "pickle"),
            (r"how.*(use|to).*(subprocess)", "subprocess"),
            (r"example.*(subprocess)", "subprocess"),
            (r"using subprocess", "subprocess"),
        ]
        for pattern, threat_name in dangerous_write_patterns:
            if re.search(pattern, task_lower, re.IGNORECASE):
                return self.failure(
                    f"🛡️ Tinku Shield: I cannot help write code using {threat_name} "
                    f"as it can be used for harmful system operations."
                )

        # ── Check API key exposure ──
        for pattern in API_KEY_PATTERNS:
            if re.search(pattern, task):
                warnings.append("⚠️ Possible API key detected — removed for your security.")
                clean_message = re.sub(pattern, "[REDACTED]", clean_message)

        # ── Check sensitive data ──
        for pattern in SENSITIVE_PATTERNS:
            if re.search(pattern, task, re.IGNORECASE):
                warnings.append("⚠️ Sensitive data detected. Please avoid sharing personal information.")

        return self.success(
            "Security check passed",
            data={"clean_message": clean_message, "warnings": warnings}
        )
