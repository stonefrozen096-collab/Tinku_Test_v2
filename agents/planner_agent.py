"""
Planner Agent — The brain of Tinku.
Breaks user requests into execution plans and assigns to correct agents.
"""
import re
import json
from .base_agent import BaseAgent


# Agent routing rules — carefully ordered to prevent overlap
AGENT_KEYWORDS = {
    # Personal questions → conversation (must check BEFORE research)
    "conversation": [
        "what is my", "what's my", "who am i", "where am i from",
        "what do i do", "my name", "do you know me", "what do you know about me",
        "tell me about me", "what did i tell", "do you remember me",
        "follow up", "continue", "update the", "change the", "what did you mean",
        "you told me", "we discussed", "last time"
    ],

    # Research — only specific research terms (removed "what is", "who is" — too broad)
    "research":     [
        "research", "latest news", "current news", "news about",
        "find information", "look up", "fact check", "search for",
        "what happened", "recent events", "today's news"
    ],

    # Writer — only report/essay specific (removed "write" — too broad)
    "writer":       [
        "generate a report", "write a report", "create a report",
        "make a report", "prepare a report", "report on", "report about",
        "write an essay", "write an article", "comprehensive report",
        "detailed report", "full report", "summarize this"
    ],

    # Code — programming specific
    "code":         [
        "code", "program", "script", "debug", "function",
        "algorithm", "python", "javascript", "java", "cpp",
        "write a program", "write code", "coding", "developer",
        "compile", "error in code", "fix this code"
    ],

    # Weather — weather specific
    "weather":      [
        "weather", "temperature", "forecast", "rain today",
        "sunny today", "humid", "climate today", "will it rain",
        "how hot", "how cold", "should i carry umbrella"
    ],

    # Finance — finance specific
    "finance":      [
        "stock price", "crypto price", "bitcoin price", "ethereum price",
        "exchange rate", "stock market", "invest in", "market today",
        "forex", "share price", "nifty", "sensex", "mutual fund"
    ],

    # Education — learning specific (removed "what does" — too broad)
    "education":    [
        "explain", "teach me", "tutor", "how does", "why does",
        "what is the concept", "help me understand", "quiz me",
        "study guide", "what does it mean", "how to learn",
        "like i am 10", "like i'm 10", "simple explanation",
        "break it down", "in simple terms"
    ],

    # Email — email specific
    "email":        [
        "write an email", "draft an email", "compose email",
        "email to my", "send email", "reply to email",
        "professional email", "formal email", "email template"
    ],

    # Creative — creative writing specific (removed "write a" — too broad)
    "creative":     [
        "write a poem", "write a story", "write a song",
        "creative writing", "imagine", "fiction", "short story",
        "poem about", "story about", "song about", "lyrics",
        "once upon a time", "creative piece", "write me a poem",
        "write me a story"
    ],

    # Resume — resume specific
    "resume":       [
        "resume", "cv", "curriculum vitae",
        "job application", "cover letter", "build my resume",
        "create my resume", "update my resume"
    ],

    # GitHub — github specific
    "github":       [
        "github.com", "analyze this repo", "analyze repository",
        "check my repo", "github repository", "pull request",
        "git commit", "analyze this github"
    ],

    # Document — file/document specific
    "document":     [
        "analyze this document", "summarize this document",
        "read this file", "extract from", "analyze file",
        "what does this document say", "this pdf"
    ],

    # URL — url specific (NEW - was missing!)
    "tool":         [
        "summarize this url", "read this url", "visit this url",
        "what does this website say", "check this link",
        "convert to pdf", "export as", "download as",
        "create pdf", "create word", "https://", "http://"
    ],

    # Knowledge base
    "knowledge":    [
        "remember this", "save this", "note this",
        "recall", "what did i save", "retrieve my notes",
        "save for later", "store this"
    ],

    # Deployment
    "deployment":   [
        "server status", "is tinku up", "check render",
        "deployment status", "build status", "service health",
        "is the server", "tinku server"
    ],

    # Analytics
    "analytics":    [
        "analytics", "usage stats", "how many times",
        "most used feature", "my activity", "usage report"
    ],
}

# Tasks that should ONLY use one specific agent
EXCLUSIVE_TASKS = {
    "write a poem":          "creative",
    "write a story":         "creative",
    "poem about":            "creative",
    "story about":           "creative",
    "write an email":        "email",
    "draft an email":        "email",
    "email to my":           "email",
    "write a program":       "code",
    "write code":            "code",
    "write a script":        "code",
    "python script":         "code",
    "debug this":            "code",
    "explain":               "education",
    "teach me":              "education",
    "like i'm 10":           "education",
    "like i am 10":          "education",
    "what is my name":       "conversation",
    "where am i from":       "conversation",
    "what do i do":          "conversation",
}

# These agents should NEVER trigger for report requests
REPORT_BLOCKLIST = ["creative", "github", "email", "code", "weather", "finance"]

# These requests should show report download card
REPORT_TRIGGERS = [
    "generate a report", "write a report", "create a report",
    "make a report", "prepare a report", "report on", "report about",
    "comprehensive report", "detailed report", "full report"
]


class PlannerAgent(BaseAgent):
    def __init__(self):
        super().__init__("PlannerAgent", "🧠", "Breaks requests into plans and routes to agents")

    def is_report_request(self, task: str) -> bool:
        """Check if this is specifically a report request."""
        task_lower = task.lower()
        return any(trigger in task_lower for trigger in REPORT_TRIGGERS)

    def detect_agents(self, task: str) -> list:
        """Detect which agents are needed for this task."""
        task_lower = task.lower()
        needed = []

        # Check exclusive tasks first — single agent only
        for phrase, agent in EXCLUSIVE_TASKS.items():
            if phrase in task_lower:
                needed = [agent]
                # Add verification for quality check
                if agent in ["writer", "code", "research"]:
                    needed.append("verification")
                return needed

        # Check conversation FIRST before anything else
        if any(kw in task_lower for kw in AGENT_KEYWORDS["conversation"]):
            return ["conversation"]

        # Check all other agents
        for agent, keywords in AGENT_KEYWORDS.items():
            if agent == "conversation":
                continue
            if any(kw in task_lower for kw in keywords):
                needed.append(agent)

        # If report request — remove blocklisted agents
        if self.is_report_request(task):
            needed = [a for a in needed if a not in REPORT_BLOCKLIST]
            # Ensure research + writer are present for reports
            if "writer" not in needed:
                needed.append("writer")

        # Default to conversation if nothing detected
        if not needed:
            needed = ["conversation"]

        # Add verification for complex tasks
        if len(needed) > 1 or any(a in needed for a in ["writer", "code", "research"]):
            if "verification" not in needed:
                needed.append("verification")

        return needed

    def is_multi_task(self, task: str) -> bool:
        """Check if request needs multiple agents working together."""
        connectors = ["and also", "then", "after that", "as well as", "additionally"]
        task_lower = task.lower()
        return any(c in task_lower for c in connectors) and len(self.detect_agents(task)) > 1

    async def run(self, task: str, context: dict) -> dict:
        """Create execution plan for the task."""
        agents_needed = self.detect_agents(task)
        is_multi = self.is_multi_task(task)
        is_report = self.is_report_request(task)

        plan = {
            "task": task,
            "agents": agents_needed,
            "is_multi_task": is_multi,
            "is_report": is_report,
            "steps": []
        }

        # Build execution steps
        for agent in agents_needed:
            if agent != "verification":
                plan["steps"].append({
                    "agent": agent,
                    "status": "pending"
                })

        # Verification always last
        if "verification" in agents_needed:
            plan["steps"].append({
                "agent": "verification",
                "status": "pending"
            })

        return self.success(
            f"Plan created: {len(plan['steps'])} steps using {', '.join(agents_needed)}",
            data=plan
        )
