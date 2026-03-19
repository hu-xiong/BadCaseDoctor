# llm/factory.py
from .openai_llm import OpenAILLM
from .qwen_llm import QwenLLM
from .zhipu_llm import ZhipuLLM
from config import Config

def get_llm(provider: str = None, model: str = None):
    print(f"[LLM-FACTORY] 请求参数 - provider: {provider}, model: {model}")
    
    # 若请求里带了 model，按模型名推断 provider，实现「选哪个用哪个」
    if model:
        ml = model.lower()
        if "glm" in ml:
            # 下拉框选 GLM-*：按你的要求走百炼（复用 Qwen/DashScope key），统一用 QwenLLM 承载
            provider = "qwen"
        elif "ernie" in ml:
            provider = "qianfan"
        elif "qwen" in ml:
            provider = "qwen"
        print(f"[LLM-FACTORY] 根据模型名推断 provider: {provider}")
    
    provider = provider or Config.DEFAULT_LLM
    print(f"[LLM-FACTORY] 最终 provider: {provider}")

    if provider == "zhipu":
        print(f"[LLM-FACTORY] 创建 ZhipuLLM, model: {model}")
        return ZhipuLLM(model=model)
    elif provider == "openai":
        print(f"[LLM-FACTORY] 创建 OpenAILLM")
        return OpenAILLM()
    elif provider == "qwen":
        # 步骤推理 / 对话 Agent：千问 3.5 Plus（DashScope）
        final_model = model or Config.DASHSCOPE_MODEL
        print(f"[LLM-FACTORY] 创建 QwenLLM, model 参数：{model}, final_model: {final_model}, 配置：{Config.DASHSCOPE_MODEL}")
        llm_instance = QwenLLM(model=final_model)
        print(f"[LLM-FACTORY] QwenLLM 实例创建完成，实例.model: {llm_instance.model}")
        return llm_instance
    elif provider == "qianfan":
        from .qianfan_llm import QianfanLLM
        print(f"[LLM-FACTORY] 创建 QianfanLLM, model: {model}")
        return QianfanLLM(model=model)
    else:
        print(f"[LLM-FACTORY] 使用默认 ZhipuLLM, model: {model}")
        return ZhipuLLM(model=model)  # 默认使用智谱 GLM