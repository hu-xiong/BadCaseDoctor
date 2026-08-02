# -*- coding: utf-8 -*-
import asyncio

from agents.cdp.auto_run_testcase import maybe_auto_run_testcases, cdp_auto_run_testcase_enabled


class _FakeCdp:
    def __init__(self):
        self.calls = []

    async def execute(self, action=None, **kwargs):
        self.calls.append((action, kwargs))
        return {
            "success": True,
            "pass_count": 2,
            "fail_count": 0,
            "session_id": kwargs.get("session_id") or "s1",
            "summary": "ok",
        }


class _FakeEngine:
    def __init__(self, tool):
        self.tools = {"cdp": tool}
        self.user_id = 1


def test_auto_run_on_navigate():
    assert cdp_auto_run_testcase_enabled()
    tool = _FakeCdp()
    engine = _FakeEngine(tool)
    rctx = {
        "cdp_test_run_id": "run-1",
        "cdp_test_run": {
            "id": "run-1",
            "mode": "testcase",
            "spec_json": {
                "testcases": [
                    {"id": 9, "title": "t", "steps": [{"step": "点击登录", "expected": "ok"}]}
                ]
            },
        },
    }
    obs = {"success": True, "session_id": "s1"}

    async def _run():
        return await maybe_auto_run_testcases(
            engine,
            obs,
            action="navigate",
            project_id=1,
            result_context=rctx,
        )

    out = asyncio.run(_run())
    assert out.get("cdp_auto_run_testcase", {}).get("ran") is True
    assert tool.calls and tool.calls[0][0] == "run_testcase"
    assert rctx.get("_cdp_testcase_auto_ran") is True


def test_skip_advise_mode_manual():
    tool = _FakeCdp()
    engine = _FakeEngine(tool)
    rctx = {
        "cdp_test_run_id": "run-2",
        "cdp_test_run": {"id": "run-2", "mode": "manual", "spec_json": {"testcases": []}},
    }

    async def _run():
        return await maybe_auto_run_testcases(
            engine,
            {"success": True},
            action="navigate",
            result_context=rctx,
        )

    out = asyncio.run(_run())
    assert "cdp_auto_run_testcase" not in out
    assert not tool.calls
