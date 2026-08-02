# -*- coding: utf-8 -*-
import asyncio

from agents.tools.accuracy_tester_tool import AccuracyTesterTool


class _FakeLLM:
    async def chat(self, prompt: str, history=None) -> str:
        if "只输出 JSON" in prompt or "测试评判员" in prompt:
            return '{"pass": true, "score": 0.88, "reason": "语义一致"}'
        return "欢迎登录系统"


def test_compare_contains():
    tool = AccuracyTesterTool(_FakeLLM())

    async def _run():
        return await tool.execute(
            test_set=[
                {
                    "name": "c1",
                    "input": "登录成功提示是什么",
                    "expected": "欢迎",
                    "actual": "页面显示：欢迎回来",
                }
            ],
            test_type="compare",
            use_llm_judge=False,
        )

    out = asyncio.run(_run())
    assert out["passed"] == 1
    assert out["accuracy"] == 100.0


def test_conversation_generates_answer():
    tool = AccuracyTesterTool(_FakeLLM())

    async def _run():
        return await tool.execute(
            test_set=[
                {
                    "name": "q1",
                    "input": "登录后看到什么",
                    "expected": "欢迎登录系统",
                }
            ],
            test_type="conversation",
            use_llm_judge=False,
        )

    out = asyncio.run(_run())
    assert out["total"] == 1
    assert out["passed"] == 1
    assert out["details"][0]["actual"]


def test_mismatch_creates_badcase():
    tool = AccuracyTesterTool(_FakeLLM())

    async def _run():
        return await tool.execute(
            test_set=[
                {
                    "name": "bad",
                    "input": "x",
                    "expected": "完全不同的期望答案XYZ",
                    "actual": "无关内容ABC",
                }
            ],
            test_type="compare",
            use_llm_judge=False,
            project_id=1,
            create_badcase_preview=True,
        )

    out = asyncio.run(_run())
    assert out["failed"] == 1
    assert len(out["badcases"]) == 1
    assert out["create_previews"]
    assert out["create_previews"][0]["target"] == "badcase"
    assert out["create_previews"][0]["confirmation_required"] is True
