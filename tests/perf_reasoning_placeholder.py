import asyncio
import time
import os
import sys

# 确保可以从项目根目录 import app/agents
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app import db
from llm.factory import get_llm
from agents.intelligent_devops_agent import IntelligentDevOpsAgent


async def main():
    llm = get_llm(model="glm-5")
    agent = IntelligentDevOpsAgent(llm=llm, db_session=db.session)
    t0 = time.perf_counter()
    async for ch in agent.handle_user_request_stream("perf placeholder", project_id=1, plan_id=None):
        if isinstance(ch, dict) and ch.get("type") == "step":
            ev = ch.get("data") or {}
            if isinstance(ev, dict) and ev.get("event") == "reasoning":
                dt_ms = (time.perf_counter() - t0) * 1000
                print(f"first_step_reasoning_ms={dt_ms:.1f}")
                return
    print("first_step_reasoning_ms=0.0")


if __name__ == "__main__":
    asyncio.run(main())

