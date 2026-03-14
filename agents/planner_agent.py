"""
Planner Agent — The brain of Tinku.
Breaks user requests into execution plans and assigns to correct agents.
"""
import re
import json
from .base_agent import BaseAgent


# Agent routing rules
AGENT_KEYWORDS = {
    "research":     ["research", "find", "search", "news", "latest", "what is", "who is", "fact"],
    "writer":       ["report", "essay", "article", "write", "draft", "summarize", "summary"],
    "code":         ["code", "program", "script", "debug", "function", "algorithm", "python", "javascript"],
    "weather":      ["weather", "temperature", "forecast", "rain", "sunny", "humid", "climate today"],
    "finance":      ["stock", "crypto", "bitcoin", "price", "exchange rate", "invest", "market", "forex"],
    "education":    ["explain", "teach", "tutor", "learn", "understand", "quiz", "study", "what does"],
    "email":        ["email", "mail", "draft email", "write email", "reply to", "compose"],
    "creative":     ["story", "poem", "creative", "imagine", "fiction", "song", "lyrics", "write a"],
    "resume":       ["resume", "cv", "curriculum vitae", "job application", "cover letter"],
    "github":       ["github", "repository", "repo", "commit", "readme", "pull request"],
    "document":     ["document", "pdf", "upload", "file", "analyze file", "extract"],
    "knowledge":    ["remember this", "save this", "note this", "recall", "what did i save"],
    "tool":         ["convert to", "export as", "download as", "create pdf", "create word"],
    "conversation": ["follow up", "continue", "update the", "change the", "what did you mean"],
    "deployment":   ["deployment", "server status", "is tinku up", "render", "deploy", "build status", "service health"],
    "analytics":    ["analytics", "usage stats", "how many times", "most used", "activity"],
}


class PlannerAgent(BaseAgent):
    def __init__(self):
        super().__init__("PlannerAgent", "🧠", "Breaks requests into plans and routes to agents")

    def detect_agents(self, task: str) -> list:
        """Detect which agents are needed for this task."""
        task_lower = task.lower()
        needed = []

        for agent, keywords in AGENT_KEYWORDS.items():
            if any(kw in task_lower for kw in keywords):
                needed.append(agent)

        # Default to conversation if nothing detected
        if not needed:
            needed = ["conversation"]

        # Always add verification for complex tasks
        if len(needed) > 1 or any(a in needed for a in ["writer", "code", "research"]):
            needed.append("verification")

        return needed

    def is_multi_task(self, task: str) -> bool:
        """Check if request needs multiple agents working together."""
        connectors = ["and", "also", "then", "after that", "as well as", "plus", "additionally"]
        task_lower = task.lower()
        return any(c in task_lower for c in connectors) and len(self.detect_agents(task)) > 1

    async def run(self, task: str, context: dict) -> dict:
        """Create execution plan for the task."""
        agents_needed = self.detect_agents(task)
        is_multi = self.is_multi_task(task)

        plan = {
            "task": task,
            "agents": agents_needed,
            "is_multi_task": is_multi,
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
