import os
import sys
import time
import asyncio


def main():
    # 确保可从项目根目录导入
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    from llm.qwen_llm import QwenLLM
    from config import Config
    import dashscope
    from dashscope import Generation

    model = os.getenv("QWEN_MODEL", "qwen3.5-plus")
    prompt = os.getenv("QWEN_PROMPT", "请只回复 ok（小写），不要输出其它内容。")

    print("=== QWEN qwen3.5-plus ping ===")
    print("model:", model)
    print("prompt:", prompt)
    print("DASHSCOPE_API_KEY set:", bool(getattr(Config, "DASHSCOPE_API_KEY", None) or getattr(Config, "QWEN_API_KEY", None)))

    # 1) 走你项目的 QwenLLM 封装（与线上一致）
    llm = QwenLLM(model=model)

    async def _run_llm():
        t0 = time.time()
        try:
            resp = await llm.parse_intent(prompt)
            dt = time.time() - t0
            print(f"\n[QwenLLM.parse_intent] elapsed_s={dt:.2f}")
            print("resp:", resp)
        except Exception as e:
            dt = time.time() - t0
            print(f"\n[QwenLLM.parse_intent] EXCEPTION elapsed_s={dt:.2f} err={e}")

    asyncio.run(_run_llm())

    # 2) 直接用 DashScope Generation.call（绕开封装，便于看到原始字段）
    print("\n=== DashScope Generation.call raw ===")
    dashscope.api_key = getattr(Config, "DASHSCOPE_API_KEY", None) or Config.QWEN_API_KEY
    t1 = time.time()
    try:
        raw = Generation.call(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            result_format="message",
        )
        dt = time.time() - t1
        print(f"elapsed_s={dt:.2f}")
        print("status_code:", getattr(raw, "status_code", None))
        print("code:", getattr(raw, "code", None))
        print("message:", getattr(raw, "message", None))
        print("request_id:", getattr(raw, "request_id", None))
        try:
            content = raw.output.choices[0].message.content
        except Exception:
            content = None
        print("content:", content)
    except Exception as e:
        dt = time.time() - t1
        print(f"EXCEPTION elapsed_s={dt:.2f} err={e}")


if __name__ == "__main__":
    main()

