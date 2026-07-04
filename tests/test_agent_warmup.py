import threading
from unittest.mock import MagicMock, patch

from routers.agent import (
    _REACT_CACHE_LOCK,
    _REACT_LLM_CACHE,
    _WARMUP_IN_FLIGHT,
    _get_cached_llm,
    _warmup_model_keys,
    schedule_react_agent_bootstrap_at_startup,
    schedule_react_agent_warmup,
)


def test_warmup_model_keys_dedupe():
    with patch("routers.agent.resolve_route", return_value="deepseek-v4-flash"):
        keys = _warmup_model_keys()
    assert keys[0] == "deepseek-v4-flash"
    assert keys.count("deepseek-v4-flash") == 1
    assert "deepseek-v4-pro" in keys


def test_schedule_warmup_skips_cached_llm():
    app = MagicMock()
    app.app_context.return_value.__enter__ = MagicMock(return_value=None)
    app.app_context.return_value.__exit__ = MagicMock(return_value=False)
    with _REACT_CACHE_LOCK:
        _REACT_LLM_CACHE.clear()
        _WARMUP_IN_FLIGHT.clear()
        _REACT_LLM_CACHE["deepseek-v4-flash"] = MagicMock()
    with patch("routers.agent._warmup_model_keys", return_value=["deepseek-v4-flash"]):
        assert schedule_react_agent_warmup(app) is False


def test_startup_bootstrap_only_once():
    app = MagicMock()
    ctx = MagicMock()
    app.app_context.return_value = ctx
    ctx.__enter__ = MagicMock(return_value=None)
    ctx.__exit__ = MagicMock(return_value=False)
    with patch("routers.agent._startup_bootstrap_enabled", return_value=True):
        with patch("routers.agent.bootstrap_react_agent_at_startup", return_value=True) as mock_boot:
            assert schedule_react_agent_bootstrap_at_startup(app) is True
            assert schedule_react_agent_bootstrap_at_startup(app) is False
            assert mock_boot.call_count == 1


def test_schedule_warmup_starts_background_thread():
    app = MagicMock()
    ctx = MagicMock()
    app.app_context.return_value = ctx
    ctx.__enter__ = MagicMock(return_value=None)
    ctx.__exit__ = MagicMock(return_value=False)
    with _REACT_CACHE_LOCK:
        _REACT_LLM_CACHE.clear()
        _WARMUP_IN_FLIGHT.clear()
    with patch("routers.agent._warmup_model_keys", return_value=["deepseek-v4-flash"]):
        with patch("routers.agent._get_cached_llm") as mock_get:
            scheduled = schedule_react_agent_warmup(app)
            assert scheduled is True
            for t in threading.enumerate():
                if t.name == "react-agent-warmup":
                    t.join(timeout=3.0)
                    break
            mock_get.assert_called()


def test_get_cached_llm_no_lock_deadlock():
    with _REACT_CACHE_LOCK:
        _REACT_LLM_CACHE.clear()
    fake_llm = MagicMock()
    with patch("routers.agent.get_llm", return_value=fake_llm):
        done = threading.Event()
        err = []

        def worker():
            try:
                _get_cached_llm("deepseek-v4-flash")
            except Exception as ex:
                err.append(ex)
            finally:
                done.set()

        t = threading.Thread(target=worker)
        t.start()
        assert done.wait(timeout=5.0), "get_cached_llm deadlocked"
        t.join(timeout=1.0)
        assert not err
