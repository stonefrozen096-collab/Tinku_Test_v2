"""
Notification Agent — Sends alerts when tasks complete.
Triggers toast notifications in the UI.
"""
from .base_agent import BaseAgent


# Events that trigger notifications
NOTIFICATION_TRIGGERS = {
    "report":    ("📊", "Report generated successfully!"),
    "resume":    ("📋", "Resume is ready to download!"),
    "code":      ("💻", "Code executed successfully!"),
    "email":     ("📧", "Email drafted and ready!"),
    "research":  ("🔬", "Research completed!"),
    "weather":   ("🌤", "Weather data fetched!"),
    "finance":   ("📈", "Financial data ready!"),
    "document":  ("📄", "Document analyzed!"),
    "github":    ("🐙", "GitHub analysis complete!"),
    "creative":  ("🎨", "Creative writing done!"),
    "education": ("📚", "Explanation ready!"),
    "knowledge": ("🧠", "Knowledge saved!"),
}


class NotificationAgent(BaseAgent):
    def __init__(self):
        super().__init__("NotificationAgent", "🔔", "Sends task completion alerts")

    async def run(self, task: str, context: dict) -> dict:
        try:
            completed_agents = context.get("completed_agents", [])
            notifications = []

            for agent_name in completed_agents:
                if agent_name in NOTIFICATION_TRIGGERS:
                    emoji, message = NOTIFICATION_TRIGGERS[agent_name]
                    notifications.append({
                        "emoji": emoji,
                        "message": message,
                        "agent": agent_name
                    })

            return self.success(
                f"{len(notifications)} notifications queued",
                data={"notifications": notifications}
            )
        except Exception as e:
            return self.failure(f"Notification agent failed: {str(e)}")
