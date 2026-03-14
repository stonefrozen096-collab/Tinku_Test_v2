"""
Finance Agent — Stocks, crypto, exchange rates, financial analysis.
"""
import re
from .base_agent import BaseAgent
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from providers import get_stock_price, get_exchange_rate, extract_stock_query


class FinanceAgent(BaseAgent):
    def __init__(self):
        super().__init__("FinanceAgent", "📊", "Stocks, crypto, exchange rates")

    async def run(self, task: str, context: dict) -> dict:
        try:
            task_lower = task.lower()
            if any(w in task_lower for w in ["exchange", "currency", "usd", "inr", "eur", "forex"]):
                result = await get_exchange_rate()
            else:
                query = extract_stock_query(task)
                result = await get_stock_price(query)
            return self.success(
                result["data"],
                sources=result.get("sources", [])
            )
        except Exception as e:
            return self.failure(f"Finance data failed: {str(e)}")
