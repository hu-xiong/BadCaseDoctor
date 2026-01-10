# agents/test_agent.py
from .base import BaseAgent

class TestAgent(BaseAgent):
    name = "test"

    def handle(self, message: str = "") -> dict:
        return {"response": f"[TEST] Echo: {message}"}