"""
Task Manager — Orchestrates all agents.
Routes tasks, manages execution, combines results.
This is the core of Tinku's multi-agent system.
"""
import json
from typing import AsyncGenerator
from .planner_agent    import PlannerAgent
from .security_agent   import SecurityAgent
from .research_agent   import ResearchAgent
from .writer_agent     import WriterAgent
from .code_agent       import CodeAgent
from .weather_agent    import WeatherAgent
from .finance_agent    import FinanceAgent
from .education_agent  import EducationAgent
from .email_agent      import EmailAgent
from .creative_agent   import CreativeAgent
from .resume_agent     import ResumeAgent
from .github_agent     import GitHubAgent
from .document_agent   import DocumentAgent
from .knowledge_agent  import KnowledgeAgent
from .tool_agent       import ToolAgent
from .conversation_agent  import ConversationAgent
from .verification_agent  import VerificationAgent
from .notification_agent  import NotificationAgent
from .analytics_agent     import AnalyticsAgent
from .learning_agent      import LearningAgent
from .deployment_agent    import DeploymentAgent


class TaskManager:
    """
    Central orchestrator for all Tinku agents.
    Usage:
        tm = TaskManager()
        async for event in tm.process(message, context):
            yield event
    """

    def __init__(self):
        self.planner      = PlannerAgent()
        self.security     = SecurityAgent()
        self.agents = {
            "research":     ResearchAgent(),
            "writer":       WriterAgent(),
            "code":         CodeAgent(),
            "weather":      WeatherAgent(),
            "finance":      FinanceAgent(),
            "education":    EducationAgent(),
            "email":        EmailAgent(),
            "creative":     CreativeAgent(),
            "resume":       ResumeAgent(),
            "github":       GitHubAgent(),
            "document":     DocumentAgent(),
            "knowledge":    KnowledgeAgent(),
            "tool":         ToolAgent(),
            "conversation": ConversationAgent(),
            "verification":  VerificationAgent(),
            "notification":  NotificationAgent(),
            "analytics":     AnalyticsAgent(),
            "learning":      LearningAgent(),
            "deployment":    DeploymentAgent(),
        }

    def sse(self, event_type: str, **kwargs) -> str:
        """Create SSE event string."""
        data = {"type": event_type, **kwargs}
        return f"data: {json.dumps(data)}\n\n"

    def step(self, emoji: str, text: str, status: str = "running") -> str:
        return self.sse("step", emoji=emoji, text=text, status=status)

    async def process(self, message: str, context: dict) -> AsyncGenerator[str, None]:
        """
        Main entry point. Processes a message through the agent pipeline.
        Yields SSE events for streaming to frontend.
        """
        all_sources = []
        agent_results = {}
        data_message = message

        # ── STEP 1: Security Check ──
        yield self.step("🔒", "Security check...", "running")
        security_result = await self.security.run(message, context)
        if not security_result["success"]:
            yield self.step("🔒", "Security check...", "done")
            yield self.sse("chunk", text=security_result["result"])
            yield self.sse("done", conversation_id=context.get("conv_id", ""))
            return

        # Use cleaned message from security agent
        clean_message = security_result["data"].get("clean_message", message)
        warnings = security_result["data"].get("warnings", [])
        yield self.step("🔒", "Security check...", "done")

        for warning in warnings:
            yield self.sse("chunk", text=f"{warning}\n\n")

        # ── STEP 2: Planning ──
        yield self.step("🧠", "Planning execution...", "running")
        plan_result = await self.planner.run(clean_message, context)
        plan = plan_result["data"]
        agents_to_run = [s["agent"] for s in plan["steps"] if s["agent"] != "verification"]
        yield self.step("🧠", "Planning execution...", "done")

        # ── STEP 3: Run Each Agent ──
        research_data = ""

        for agent_name in agents_to_run:
            agent = self.agents.get(agent_name)
            if not agent:
                continue

            step_text = f"{agent.name} working..."
            yield self.step(agent.emoji, step_text, "running")

            # Pass research data to writer agent
            agent_context = {**context}
            if agent_name == "writer" and research_data:
                agent_context["research_data"] = research_data

            result = await agent.run(clean_message, agent_context)

            if result["success"]:
                agent_results[agent_name] = result["result"]
                all_sources.extend(result.get("sources", []))

                # Store research for writer
                if agent_name == "research":
                    research_data = result["result"]

            # Use SAME text so frontend can match and update to tick
            yield self.step(agent.emoji, step_text, "done")

        # ── STEP 4: Combine Results ──
        if not agent_results:
            # Fallback to conversation agent
            yield self.step("💬", "Generating response...", "running")
            conv_result = await self.agents["conversation"].run(clean_message, context)
            final_response = conv_result["result"]
            yield self.step("💬", "Generating response...", "done")
        elif len(agent_results) == 1:
            # Single agent result
            final_response = list(agent_results.values())[0]
        else:
            # Multiple agents — combine intelligently
            yield self.step("⚡", "Combining results...", "running")
            combined = "\n\n".join([
                f"**{name.title()} Results:**\n{result}"
                for name, result in agent_results.items()
            ])
            final_response = combined
            yield self.step("⚡", "Combining results...", "done")

        # ── STEP 5: Verification ──
        if "verification" in [s["agent"] for s in plan["steps"]]:
            yield self.step("✅", "Verifying response...", "running")
            verify_context = {
                **context,
                "response_to_verify": final_response,
                "original_question": clean_message
            }
            verify_result = await self.agents["verification"].run(clean_message, verify_context)
            final_response = verify_result["result"]
            yield self.step("✅", "Verifying response...", "done")

        # ── STEP 6: Stream Final Response ──
        yield self.step("✨", "Generating response...", "running")

        # Stream response word by word for smooth UX
        words = final_response.split(" ")
        chunk_size = 5
        for i in range(0, len(words), chunk_size):
            chunk = " ".join(words[i:i+chunk_size]) + " "
            yield self.sse("chunk", text=chunk)

        yield self.step("✨", "Generating response...", "done")

        # ── Send Sources ──
        if all_sources:
            seen = set()
            unique = []
            for s in all_sources:
                key = s.get("url") or s.get("title") or str(s)
                if key not in seen:
                    seen.add(key)
                    unique.append(s)
            yield self.sse("sources", sources=unique)

        # ── Check if report ──
        plan_agents = plan.get("agents", [])
        if "writer" in plan_agents:
            yield self.sse("report", content=final_response)

        # ── Notifications ──
        completed = [s["agent"] for s in plan["steps"] if s["agent"] not in ["verification","notification","analytics","learning"]]
        notif_context = {**context, "completed_agents": completed}
        notif_result = await self.agents["notification"].run(data_message, notif_context)
        for notif in notif_result["data"].get("notifications", []):
            yield self.sse("toast", emoji=notif["emoji"], message=notif["message"])

        # ── Analytics ──
        await self.agents["analytics"].run(data_message, notif_context)

        # ── Learning ──
        learn_context = {**context, "completed_agents": completed, "response": final_response}
        await self.agents["learning"].run(data_message, learn_context)
        # Note: "done" event is sent by chat.py after DB save
