import asyncio
import json
import os
import sys
import time


def _safe_preview(val, limit: int = 800) -> str:
    try:
        s = val if isinstance(val, str) else json.dumps(val, ensure_ascii=False, default=str)
    except Exception:
        s = repr(val)
    s = s.replace("\r\n", "\n")
    return s if len(s) <= limit else (s[:limit] + " ...[truncated]")


async def main():
    # 确保能 import 项目内模块
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    from llm.factory import get_llm  # noqa

    llm = get_llm(model="qwen-max-thinking")
    prompt = "请用一句话回答：1+1 等于多少？只输出数字。"
    messages_sent = [{"role": "user", "content": prompt}]

    print("[QWEN-CHECK] ========== 发出去的消息 ==========")
    print(f"[QWEN-CHECK] prompt: {repr(prompt)}")
    print(f"[QWEN-CHECK] messages: {json.dumps(messages_sent, ensure_ascii=False, indent=2)}")
    print("[QWEN-CHECK] ======================================")

    # ===== 1) 非流式：chat_with_reasoning（便于对照）=====
    t0 = time.time()
    try:
        out = await llm.chat_with_reasoning(prompt)
    except Exception as e:
        dt = time.time() - t0
        print("[QWEN-CHECK] chat_with_reasoning 调用异常")
        print(f"[QWEN-CHECK] elapsed_s={dt:.2f}")
        print(f"[QWEN-CHECK] error={repr(e)}")
        raise

    dt = time.time() - t0
    print("[QWEN-CHECK] ========== chat_with_reasoning 回复 ==========")
    print(f"[QWEN-CHECK] 调用成功, model={getattr(llm, 'model', None)}, elapsed_s={dt:.2f}")
    print(f"[QWEN-CHECK] out (完整): {json.dumps({k: _safe_preview(v, limit=2000) for k, v in out.items()}, ensure_ascii=False, indent=2)}")
    print(f"[QWEN-CHECK] content_preview: {_safe_preview(out.get('content'))}")
    print(f"[QWEN-CHECK] reasoning_preview: {_safe_preview(out.get('reasoning_content'))}")
    print("[QWEN-CHECK] ======================================")

    # ===== 2) 流式：chat_stream_with_reasoning（核心验证：reasoning_delta 是否有产出）=====
    if not hasattr(llm, "chat_stream_with_reasoning"):
        print("[QWEN-CHECK] 当前 LLM 不支持 chat_stream_with_reasoning，跳过流式测试。")
        return

    print("\n[QWEN-CHECK] ========== chat_stream_with_reasoning 流式开始 ==========")
    t1 = time.time()
    reasoning_parts = []
    content_parts = []
    n_reasoning = 0
    n_content = 0
    n_other = 0

    try:
        for item in llm.chat_stream_with_reasoning(prompt):
            if not isinstance(item, dict):
                n_other += 1
                continue
            tp = item.get("type")
            if tp == "reasoning_delta":
                delta = item.get("delta")
                if isinstance(delta, str) and delta:
                    reasoning_parts.append(delta)
                    n_reasoning += 1
                    # 实时打印（不截断），方便看换行是否正常
                    print(delta, end="", flush=True)
            elif tp == "content_delta":
                delta = item.get("delta")
                if isinstance(delta, str) and delta:
                    content_parts.append(delta)
                    n_content += 1
            elif tp == "done":
                break
            else:
                n_other += 1
    except Exception as e:
        dt2 = time.time() - t1
        print("\n[QWEN-CHECK] chat_stream_with_reasoning 调用异常")
        print(f"[QWEN-CHECK] elapsed_s={dt2:.2f}")
        print(f"[QWEN-CHECK] error={repr(e)}")
        raise

    dt2 = time.time() - t1
    reasoning_full = "".join(reasoning_parts)
    content_full = "".join(content_parts)
    print("\n[QWEN-CHECK] ========== chat_stream_with_reasoning 流式结束 ==========")
    print(f"[QWEN-CHECK] elapsed_s={dt2:.2f}")
    print(f"[QWEN-CHECK] chunks: reasoning={n_reasoning}, content={n_content}, other={n_other}")
    print(f"[QWEN-CHECK] reasoning_len={len(reasoning_full)} content_len={len(content_full)}")
    print(f"[QWEN-CHECK] content_full: {repr(content_full.strip())}")
    print("[QWEN-CHECK] ======================================")


if __name__ == "__main__":
    # Windows 控制台可能是 GBK，强制 UTF-8，避免打印符号时报 UnicodeEncodeError
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    asyncio.run(main())

