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
                # Try to extract city name — skip prepositions like "in", "at", "for"
                # Pattern: look for city name AFTER preposition
                match = re.search(
                    r"(?:weather\s+in|weather\s+at|weather\s+for|in|at|for)\s+([A-Za-z]+(?:\s+[A-Za-z]+)??)(?:\s+today|\s+tomorrow|\s+now|$|\?)",
                    task, re.IGNORECASE
                )
                if match:
                    city = match.group(1).strip()
                else:
                    # Fallback: find capitalized word that looks like a city
                    city_match = re.search(r"\b([A-Z][a-z]{2,})\b", task)
                    city = city_match.group(1) if city_match else "Mumbai"

            result = await get_weather(city)
            return self.success(
                result["data"],
                data={"city": city},
                sources=result.get("sources", [])
            )
        except Exception as e:
            return self.failure(f"Weather fetch failed: {str(e)}")
