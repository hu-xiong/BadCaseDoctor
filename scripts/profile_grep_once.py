import asyncio
import json
import sys
import time
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents.tools.grep_tool import GrepTool


async def main():
    tool = GrepTool()
    for n in range(1, 3):
        print(f"\n===== RUN {n} =====")
        started = time.perf_counter()
        result = await tool.execute(
            keywords="登录 bug 邮箱 不能 收到 验证码",
            project_id="1",
            plan_id="1",
            target="bug",
            user_input="登录的bug，邮箱不能收到验证码 这个bug帮我检索一下",
            ui_locale="zh",
        )
        wall = round((time.perf_counter() - started) * 1000, 1)
        print("wall_ms", wall)
        print("success", result.get("success"))
        print("grep_perf_ms", result.get("grep_perf_ms"))
        data = result.get("data") or {}
        for key in ["grep_perf_ms", "grep_meta", "hybrid_meta", "rerank_meta", "bug_location", "bug_list"]:
            value = data.get(key)
            if value is None:
                continue
            if key == "bug_list":
                print("bug_list_len", len(value or []))
                print(json.dumps((value or [])[:3], ensure_ascii=False, indent=2)[:2000])
            else:
                print(key, json.dumps(value, ensure_ascii=False, indent=2)[:4000])


if __name__ == "__main__":
    asyncio.run(main())
