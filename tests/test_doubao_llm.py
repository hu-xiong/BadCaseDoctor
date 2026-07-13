# -*- coding: utf-8 -*-
from __future__ import annotations

from unittest.mock import patch

from llm.doubao_llm import DoubaoLLM
from llm.factory import get_llm
from llm.model_registry import get_model, is_supported_model


def test_doubao_in_registry():
    assert is_supported_model("doubao-1-5-pro-32k")
    m = get_model("doubao-1-5-pro-32k")
    assert m is not None
    assert m.provider == "doubao"


def test_factory_creates_doubao_llm():
    with patch("config.Config.DOUBAO_API_KEY", "ark-test"):
        llm = get_llm(model="doubao-1-5-pro-32k")
    assert isinstance(llm, DoubaoLLM)
    assert llm.model == "doubao-1-5-pro-32k"
