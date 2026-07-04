# llm/factory.py
import logging

from .qwen_llm import QwenLLM
from .zhipu_llm import ZhipuLLM
from config import Config
from .model_registry import is_supported_model

_LLM_PROMPT_BANNER_DONE = False


def _normalize_requested_model(model: str | None) -> str | None:
    """
    只允许“注册表里已启用”的模型（前端下拉框同源），避免透传导致 invalid_model。
    """
    if not model:
        return None
    m = str(model).strip()
    if not m:
        return None
    ml = m.lower()
    # 兼容前端传 auto：具体选模在 router 层完成；factory 仅做兜底
    if ml == "auto":
        return m
    if is_supported_model(m):
        return m
    print(f"[LLM-FACTORY] 不在注册表或未启用的模型名，将忽略并回退默认模型: {m!r}")
    return None

def get_llm(provider: str = None, model: str = None):
    global _LLM_PROMPT_BANNER_DONE
    model = _normalize_requested_model(model)
    print(f"[LLM-FACTORY] 请求参数 - provider: {provider}, model: {model}")

    try:
        from .prompt_log import (
            llm_prompt_log_enabled,
            llm_prompt_log_file_path,
            react_prompt_log_enabled,
        )

        _pf = llm_prompt_log_file_path()
        if (llm_prompt_log_enabled() or react_prompt_log_enabled() or _pf) and not _LLM_PROMPT_BANNER_DONE:
            _LLM_PROMPT_BANNER_DONE = True
            parts = []
            if llm_prompt_log_enabled():
                parts.append("控制台打印 LLM 请求 JSON（LLM_LOG_PROMPTS=1）")
            if react_prompt_log_enabled():
                parts.append("ReAct 组装 prompt（REACT_PROMPT_LOG=1 或随 LLM_LOG_PROMPTS）")
            if _pf:
                parts.append(f"追加写入文件 {_pf}（LLM_PROMPT_LOG_PATH）")
            _b = "[LLM_PROMPT] 已开启：" + "；".join(parts) + "。关闭请删 .env 对应项并重启。"
            logging.getLogger("badcase.llm_prompt").warning(_b)
            print(_b, flush=True)
    except Exception:
        pass
    
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
        elif "deepseek" in ml:
            provider = "deepseek"
        elif "doubao" in ml or ml.startswith("ep-"):
            provider = "doubao"
        print(f"[LLM-FACTORY] 根据模型名推断 provider: {provider}")
    
    provider = provider or Config.DEFAULT_LLM
    if provider == "openai":
        # 兼容旧配置：OpenAI 实现已移除，统一走 DashScope 千问
        print(f"[LLM-FACTORY] provider=openai 已映射为 QwenLLM（DashScope）")
        provider = "qwen"
    print(f"[LLM-FACTORY] 最终 provider: {provider}")

    if provider == "zhipu":
        print(f"[LLM-FACTORY] 创建 ZhipuLLM, model: {model}")
        return ZhipuLLM(model=model)
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
    elif provider == "deepseek":
        from .deepseek_llm import DeepSeekLLM

        final_model = model or getattr(Config, "DEEPSEEK_V4_MODEL", None) or "deepseek-v4-pro"
        print(f"[LLM-FACTORY] 创建 DeepSeekLLM, model: {final_model}")
        return DeepSeekLLM(model=final_model)
    elif provider == "doubao":
        from .doubao_llm import DoubaoLLM

        final_model = model or getattr(Config, "DOUBAO_MODEL", None) or "doubao-1-5-pro-32k"
        print(f"[LLM-FACTORY] 创建 DoubaoLLM, model: {final_model}")
        return DoubaoLLM(model=final_model)
    else:
        print(f"[LLM-FACTORY] 使用默认 ZhipuLLM, model: {model}")
        return ZhipuLLM(model=model)  # 默认使用智谱 GLM