import time
import json
import os
import sys
import asyncio


def main():
    """
    最小化调试 GLM-5：
    - 不走 Text2SQL
    - 只验证 glm-5 是否能正常返回、耗时多少、是否报鉴权/模型不可用
    """
    # 确保可从项目根目录导入
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    from llm.factory import get_llm

    # 可通过环境变量切换：glm-5 / glm-4-flash / 其它
    model = os.getenv("GLM_MODEL", "glm-5")
    llm = get_llm(model=model)

    prompt = "请只回复 'ok'（小写），不要输出其它内容。"
    print("=== GLM-5 ping ===")
    print("prompt:", prompt)
    print("llm.class:", type(llm).__name__)
    print("llm.model:", getattr(llm, "model", None))

    async def _run():
        t0 = time.time()
        try:
            # 兼容不同实现：优先 chat_with_reasoning / chat，再退回 parse_intent
            if hasattr(llm, "chat_with_reasoning"):
                resp = llm.chat_with_reasoning(prompt)
                if asyncio.iscoroutine(resp):
                    resp = await resp
            elif hasattr(llm, "chat"):
                resp = llm.chat(prompt)
                if asyncio.iscoroutine(resp):
                    resp = await resp
            else:
                resp = llm.parse_intent(prompt)
                if asyncio.iscoroutine(resp):
                    resp = await resp
            dt = time.time() - t0
            print(f"\n耗时: {dt:.2f}s")
            print("raw:", json.dumps(resp, ensure_ascii=False, indent=2) if isinstance(resp, (dict, list)) else str(resp))
        except Exception as e:
            dt = time.time() - t0
            print(f"\n❌ 调用异常: {e}\n耗时: {dt:.2f}s")
            raise

    asyncio.run(_run())


if __name__ == "__main__":
    main()

