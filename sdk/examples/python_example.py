"""
Python SDK 使用示例
运行: cd sdk && pip install -e . && cd examples && python python_example.py
或: PYTHONPATH=../.. python python_example.py (从 examples 目录)
"""
import os
os.environ.setdefault("BADCASE_SDK_APP", "example_app")
os.environ.setdefault("BADCASE_SDK_ENV", "dev")

from badcase_sdk import init, BadCaseCollector, llm_observe, llm_span, observe_stream, install

# 1. 初始化（可选，也可用环境变量）
init(app="example_app", env="dev")

# 2. 装饰器方式
@llm_observe(provider="qwen", endpoint="chat", model="qwen-plus", streaming=False)
def call_llm_sync(prompt: str):
    # 模拟 LLM 调用
    return "Hello", {"input_tokens": 10, "output_tokens": 5, "badcase_type": "none"}

# 3. 手动采集
def manual_example():
    c = BadCaseCollector()
    c.record_request("qwen", "chat", "qwen-plus", False, "success")
    c.record_duration("qwen", "chat", "qwen-plus", False, "success", 1.5)
    c.record_tokens("qwen", "chat", "qwen-plus", "input", 100)
    c.record_tokens("qwen", "chat", "qwen-plus", "output", 50)
    c.record_badcase("qwen", "chat", "qwen-plus", False, "none")

# 4. llm_span 多段记录
def span_example():
    with llm_span(conversation_id="conv_123") as ctx:
        ctx.record_retrieval(provider="qwen", model="qwen-plus", count=5, duration=0.1)
        ctx.record_tool_call("grep", provider="qwen", model="qwen-plus", result="success")

if __name__ == "__main__":
    call_llm_sync("hello")
    manual_example()
    span_example()
    print("Example done. Check /metrics if running with FastAPI/Flask.")
