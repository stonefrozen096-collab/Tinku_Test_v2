"""
Deployment Agent — Monitors Render service health and deployment status.
"""
import os
import aiohttp
from .base_agent import BaseAgent
from datetime import datetime


RENDER_API_KEY   = os.getenv("RENDER_API_KEY", "")
RENDER_SERVICE_ID = os.getenv("RENDER_SERVICE_ID", "srv-d6hsr6dm5p6s73bpp150")


class DeploymentAgent(BaseAgent):
    def __init__(self):
        super().__init__("DeploymentAgent", "🚀", "Monitors deployment status and service health")

    async def get_service_status(self) -> dict:
        """Get Render service status via API."""
        if not RENDER_API_KEY:
            return {"status": "unknown", "message": "RENDER_API_KEY not set"}

        try:
            headers = {"Authorization": f"Bearer {RENDER_API_KEY}"}
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"https://api.render.com/v1/services/{RENDER_SERVICE_ID}",
                    headers=headers
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return {
                            "status":     data.get("serviceDetails", {}).get("status", "unknown"),
                            "name":       data.get("name", "Tinku"),
                            "url":        data.get("serviceDetails", {}).get("url", ""),
                            "updated_at": data.get("updatedAt", "")
                        }
                    return {"status": "error", "message": f"API returned {resp.status}"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    async def get_recent_deploys(self) -> list:
        """Get recent deployment history."""
        if not RENDER_API_KEY:
            return []
        try:
            headers = {"Authorization": f"Bearer {RENDER_API_KEY}"}
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"https://api.render.com/v1/services/{RENDER_SERVICE_ID}/deploys?limit=3",
                    headers=headers
                ) as resp:
                    if resp.status == 200:
                        deploys = await resp.json()
                        return [
                            {
                                "status":     d.get("deploy", {}).get("status", ""),
                                "created_at": d.get("deploy", {}).get("createdAt", ""),
                                "commit":     d.get("deploy", {}).get("commit", {}).get("message", "")[:50]
                            }
                            for d in (deploys if isinstance(deploys, list) else [])
                        ]
        except Exception:
            pass
        return []

    async def run(self, task: str, context: dict) -> dict:
        try:
            task_lower = task.lower()

            # Get service status
            status = await self.get_service_status()
            deploys = await self.get_recent_deploys()

            status_emoji = "🟢" if status.get("status") == "live" else "🔴"
            result = f"{status_emoji} Service Status: {status.get('status', 'unknown').upper()}\n"
            result += f"🌐 URL: {status.get('url', 'https://tinku-test-v2.onrender.com')}\n"

            if deploys:
                result += "\n📦 Recent Deployments:\n"
                for d in deploys:
                    deploy_emoji = "✅" if d["status"] == "live" else "❌"
                    result += f"{deploy_emoji} {d['status']} — {d['commit']}\n"

            if not RENDER_API_KEY:
                result = "⚠️ Add RENDER_API_KEY to environment variables to enable deployment monitoring.\n"
                result += "🌐 Service URL: https://tinku-test-v2.onrender.com"

            return self.success(result, data={"status": status, "deploys": deploys})

        except Exception as e:
            return self.failure(f"Deployment agent failed: {str(e)}")
