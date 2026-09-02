# llm/factory.py
import logging
import os

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


def _try_litellm_transport(model: str | None):
    """
    LLM_TRANSPORT=litellm 时走 LiteLLM 传输层（选模策略仍在 model_router）。
    文心 qianfan 无稳定兼容 base 时回退原生。
    """
    try:
        from .litellm_transport import litellm_transport_enabled, resolve_litellm_endpoint
    except Exception:
        return None
    if not litellm_transport_enabled():
        return None
    mid = (model or Config.DASHSCOPE_MODEL or "qwen3.5-plus").strip()
    if mid.lower() == "auto":
        mid = Config.DASHSCOPE_MODEL or "qwen3.5-plus"
    ep = resolve_litellm_endpoint(mid)
    if ep.provider == "qianfan" and not ep.api_base:
        print("[LLM-FACTORY] LiteLLM: qianfan 未配置 QIANFAN_COMPAT_BASE_URL，回退原生 QianfanLLM")
        return None
    try:
        from .litellm_llm import LiteLLMLLM

        print(
            f"[LLM-FACTORY] LiteLLM 传输层 model={mid!r} litellm={ep.litellm_model!r} "
            f"provider={ep.provider}",
            flush=True,
        )
        return LiteLLMLLM(model=mid)
    except ImportError as e:
        print(f"[LLM-FACTORY] LiteLLM 不可用，回退原生 SDK: {e}", flush=True)
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

    _lt = _try_litellm_transport(model)
    if _lt is not None:
        return _lt
    
    # 若请求里带了 model，按模型名推断 provider，实现「选哪个用哪个」
    if model:
        ml = model.lower()
        if "glm" in ml:
            # GLM 走智谱官方；若要用百炼托管名请显式传 provider=qwen
            provider = "zhipu"
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
        if not (getattr(Config, "DEEPSEEK_API_KEY", None) or "").strip():
            # Auto 常会选 deepseek-flash；无 key 时优先有密钥且可用的回退
            _doubao_key = (getattr(Config, "DOUBAO_API_KEY", None) or "").strip()
            _doubao_model = (getattr(Config, "DOUBAO_MODEL", None) or "").strip()
            _doubao_ok = _doubao_key and (
                _doubao_model.startswith("ep-")
                or (os.getenv("DOUBAO_ALLOW_NAMED_MODEL") or "").strip().lower()
                in ("1", "true", "yes", "on")
            )
            if _doubao_ok:
                from .doubao_llm import DoubaoLLM

                fb = _doubao_model or "doubao-1-5-pro-32k"
                print(
                    f"[LLM-FACTORY] 未配置 DEEPSEEK_API_KEY，回退 DoubaoLLM model={fb}",
                    flush=True,
                )
                return DoubaoLLM(model=fb)
            if (getattr(Config, "ZHIPU_API_KEY", None) or "").strip():
                fb = (getattr(Config, "ZHIPU_MODEL", None) or "glm-4-flash").strip()
                print(
                    f"[LLM-FACTORY] 未配置 DEEPSEEK_API_KEY，回退 ZhipuLLM model={fb}",
                    flush=True,
                )
                return ZhipuLLM(model=fb)
            if (getattr(Config, "DASHSCOPE_API_KEY", None) or os.getenv("DASHSCOPE_API_KEY") or "").strip():
                fb = model or Config.DASHSCOPE_MODEL
                print(
                    f"[LLM-FACTORY] 未配置 DEEPSEEK_API_KEY，回退 QwenLLM model={fb}",
                    flush=True,
                )
                return QwenLLM(model=fb)
            print(
                "[LLM-FACTORY] 警告：未配置 DEEPSEEK_API_KEY，且无可用回退模型",
                flush=True,
            )
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