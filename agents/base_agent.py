"""
Base Agent — All Tinku agents inherit from this.
"""
from abc import ABC, abstractmethod
from typing import Optional
import json


class BaseAgent(ABC):
    def __init__(self, name: str, emoji: str, description: str):
        self.name = name
        self.emoji = emoji
        self.description = description

    @abstractmethod
    async def run(self, task: str, context: dict) -> dict:
        """
        Run the agent on a task.
        Returns: {
            "success": bool,
            "result": str,
            "data": any,
            "sources": list
        }
        """
        pass

    def success(self, result: str, data=None, sources=None) -> dict:
        return {
            "success": True,
            "agent": self.name,
            "emoji": self.emoji,
            "result": result,
            "data": data or {},
            "sources": sources or []
        }

    def failure(self, reason: str) -> dict:
        return {
            "success": False,
            "agent": self.name,
            "emoji": self.emoji,
            "result": reason,
            "data": {},
            "sources": []
        }
