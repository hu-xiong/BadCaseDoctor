# llm/factory.py
from .openai_llm import OpenAILLM
from .qwen_llm import QwenLLM
from .zhipu_llm import ZhipuLLM
from config import Config

def get_llm(provider: str = None, model: str = None):
    provider = provider or Config.DEFAULT_LLM
    if not provider and model:
        if "glm" in model.lower():
            provider = "zhipu"
        elif "ernie" in model.lower():
            provider = "qianfan"
        else:
            provider = "qwen"
            
    if provider == "zhipu":
        return ZhipuLLM(model=model)
    elif provider == "openai":
        return OpenAILLM()
    elif provider == "qwen":
        return QwenLLM(model=model)
    elif provider == "qianfan":
        from .qianfan_llm import QianfanLLM
        return QianfanLLM(model=model)
    else:
        return ZhipuLLM(model=model)  # 默认使用智谱GLM