"""
Weather Agent — Live weather, forecasts, travel weather.
"""
import re
from .base_agent import BaseAgent
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from providers import get_weather


class WeatherAgent(BaseAgent):
    def __init__(self):
        super().__init__("WeatherAgent", "🌤", "Live weather and forecasts")

    async def run(self, task: str, context: dict) -> dict:
        try:
            # Extract city from task
            city = context.get("city", "")
            if not city:
                # Try to extract from task
                match = re.search(
                    r"(?:in|at|for|weather)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)",
                    task, re.IGNORECASE
                )
                city = match.group(1) if match else "Mumbai"

            result = await get_weather(city)
            return self.success(
                result["data"],
                data={"city": city},
                sources=result.get("sources", [])
            )
        except Exception as e:
            return self.failure(f"Weather fetch failed: {str(e)}")
