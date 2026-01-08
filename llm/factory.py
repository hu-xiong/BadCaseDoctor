# llm/factory.py
from .openai_llm import OpenAILLM
from .qwen_llm import QwenLLM
from config import Config

def get_llm(provider: str = None):
    provider = provider or Config.DEFAULT_LLM
    if provider == "openai":
        return OpenAILLM()
    elif provider == "qwen":
        return QwenLLM()
    else:
        raise ValueError(f"Unsupported LLM: {provider}")