# -*- coding: utf-8 -*-
from llm.litellm_transport import (
    fallback_model_ids,
    litellm_transport_enabled,
    resolve_litellm_endpoint,
)


def test_litellm_transport_flag(monkeypatch):
    monkeypatch.delenv("LLM_TRANSPORT", raising=False)
    assert litellm_transport_enabled() is False
    monkeypatch.setenv("LLM_TRANSPORT", "litellm")
    assert litellm_transport_enabled() is True


def test_resolve_qwen_dashscope(monkeypatch):
    monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-test")
    monkeypatch.setenv(
        "DASHSCOPE_COMPAT_BASE_URL",
        "https://dashscope.aliyuncs.com/compatible-mode/v1",
    )
    ep = resolve_litellm_endpoint("qwen3.5-plus")
    assert ep.provider == "qwen"
    assert ep.litellm_model == "openai/qwen3.5-plus"
    assert "dashscope" in (ep.api_base or "")
    assert ep.api_key == "sk-test"


def test_resolve_glm_via_dashscope(monkeypatch):
    monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-test")
    ep = resolve_litellm_endpoint("glm-5")
    assert ep.provider == "qwen"
    assert ep.litellm_model == "openai/glm-5"


def test_resolve_deepseek(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "ds-key")
    monkeypatch.setenv("DEEPSEEK_API_BASE_URL", "https://api.deepseek.com")
    ep = resolve_litellm_endpoint("deepseek-v4-pro")
    assert ep.provider == "deepseek"
    assert ep.litellm_model == "openai/deepseek-v4-pro"
    assert ep.api_key == "ds-key"


def test_fallback_model_ids(monkeypatch):
    monkeypatch.setenv("LITELLM_FALLBACK_MODELS", "qwen3.5-plus, deepseek-v4-flash, qwen3.5-plus")
    ids = fallback_model_ids("qwen3.5-plus")
    assert ids == ["deepseek-v4-flash"]


def test_factory_litellm_path(monkeypatch):
    monkeypatch.setenv("LLM_TRANSPORT", "litellm")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-test")

    class _FakeLite:
        def __init__(self, model=None):
            self.model = model

    import llm.factory as factory

    monkeypatch.setattr("llm.litellm_llm.LiteLLMLLM", _FakeLite)
    # 避免真 import litellm
    monkeypatch.setattr(
        "llm.litellm_llm._import_litellm",
        lambda: type("L", (), {"suppress_debug_info": True})(),
    )
    llm = factory.get_llm(model="qwen3.5-plus")
    assert isinstance(llm, _FakeLite)
    assert llm.model == "qwen3.5-plus"
