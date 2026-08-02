# agents/tools/accuracy_tester_tool.py
"""
准确率测试工具：对比 expected vs actual（含 LLM 评分），可从 TestCase/BadCase 拉样本。
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from ..tool_registry import BaseTool


class AccuracyTesterTool(BaseTool):
    """准确率测试工具"""

    def __init__(self, llm):
        super().__init__(
            name="accuracy_tester",
            description=(
                "测试问答/答案准确率：对比 expected 与 actual，输出准确率与 BadCase 列表。"
                "可传 test_set=[{name,input,expected,actual?}]，或 testcase_ids/badcase_ids+project_id 从库加载。"
                "test_type: conversation|functional|compare（已有 actual 时用 compare）。"
            ),
        )
        self.llm = llm

    async def execute(
        self,
        test_set: Optional[List[Dict[str, Any]]] = None,
        feature: str = "",
        test_type: str = "conversation",
        project_id: Any = None,
        testcase_ids: Optional[List[Any]] = None,
        badcase_ids: Optional[List[Any]] = None,
        use_llm_judge: bool = True,
        create_badcase_preview: bool = True,
        **kwargs,
    ) -> Dict[str, Any]:
        feature = str(feature or kwargs.get("feature_name") or "accuracy").strip() or "accuracy"
        ttype = (test_type or "conversation").strip().lower()
        if ttype in ("qa", "chat", "问答"):
            ttype = "conversation"
        if ttype in ("func",):
            ttype = "functional"
        if kwargs.get("create_badcase_preview") is False:
            create_badcase_preview = False

        samples = list(test_set or [])
        if not samples:
            samples = self._load_samples_from_db(
                project_id=project_id,
                testcase_ids=testcase_ids,
                badcase_ids=badcase_ids,
            )

        results: Dict[str, Any] = {
            "success": True,
            "feature": feature,
            "test_type": ttype,
            "total": len(samples),
            "passed": 0,
            "failed": 0,
            "accuracy": 0.0,
            "badcases": [],
            "details": [],
            "create_previews": [],
        }
        if not samples:
            results["success"] = False
            results["error"] = "无测试样本：请提供 test_set 或 testcase_ids/badcase_ids"
            return results

        for i, test in enumerate(samples):
            name = str(test.get("name") or test.get("title") or f"Test {i + 1}")
            expected = test.get("expected")
            if expected is None:
                expected = test.get("correct_answer") or test.get("expected_result") or ""
            expected = self._as_text(expected)
            inp = test.get("input") or test.get("question") or test.get("prompt") or ""

            actual = test.get("actual")
            if actual is None and ttype != "compare":
                actual = await self._execute_test(test, ttype, inp)
            actual = self._as_text(actual)

            ok, score, reason = await self._compare_results(
                actual, expected, use_llm_judge=use_llm_judge, question=str(inp)
            )
            detail = {
                "name": name,
                "input": inp,
                "expected": expected,
                "actual": actual,
                "passed": ok,
                "score": score,
                "reason": reason,
            }
            results["details"].append(detail)
            if ok:
                results["passed"] += 1
            else:
                results["failed"] += 1
                results["badcases"].append({
                    "name": name,
                    "input": inp,
                    "expected": expected,
                    "actual": actual,
                    "diff": await self._compute_diff(expected, actual),
                    "score": score,
                    "reason": reason,
                    "source_id": test.get("id") or test.get("source_id"),
                    "source_type": test.get("source_type"),
                })

        total = results["total"]
        results["accuracy"] = (results["passed"] / total * 100.0) if total else 0.0
        results["summary"] = (
            f"{feature}: {results['passed']}/{total} 通过，准确率 {results['accuracy']:.1f}%"
        )

        if create_badcase_preview and results["badcases"] and project_id is not None:
            try:
                pid = int(project_id)
            except (TypeError, ValueError):
                pid = None
            if pid is not None:
                results["create_previews"] = self._build_badcase_create_previews(
                    results["badcases"],
                    project_id=pid,
                    plan_id=kwargs.get("plan_id"),
                    feature=feature,
                )
        return results

    def _build_badcase_create_previews(
        self,
        badcases: List[Dict[str, Any]],
        *,
        project_id: int,
        plan_id: Any = None,
        feature: str = "",
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        """构造 create 工具预览形态，供前端采纳落库。"""
        previews: List[Dict[str, Any]] = []
        for bc in (badcases or [])[:limit]:
            title = str(bc.get("name") or "准确率失败").strip()[:120]
            if feature:
                title = f"[{feature}] {title}"[:120]
            fields: Dict[str, Any] = {
                "title": title,
                "base_problem": str(bc.get("input") or "")[:2000],
                "answer": str(bc.get("actual") or "")[:2000],
                "correct_answer": str(bc.get("expected") or "")[:2000],
                "case_category": "功能缺陷",
                "priority": "p3",
            }
            if plan_id is not None:
                try:
                    fields["plan_id"] = int(plan_id)
                except (TypeError, ValueError):
                    pass
            previews.append({
                "success": True,
                "confirmation_required": True,
                "tool": "create",
                "target": "badcase",
                "project_id": int(project_id),
                "fields": fields,
                "preview": fields,
                "message": "准确率测评失败项 → BadCase 预览（确认后落库）",
                "source": "accuracy_tester",
            })
        return previews

    def _load_samples_from_db(
        self,
        *,
        project_id: Any,
        testcase_ids: Optional[List[Any]],
        badcase_ids: Optional[List[Any]],
    ) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        try:
            from flask import has_app_context

            if not has_app_context():
                return out
            from db_extensions import db
        except Exception:
            return out

        pid = None
        if project_id is not None:
            try:
                pid = int(project_id)
            except (TypeError, ValueError):
                pid = None

        if testcase_ids:
            try:
                from models.orm import TestCase

                ids = [int(x) for x in testcase_ids if x is not None]
                q = db.session.query(TestCase).filter(TestCase.id.in_(ids))
                if pid is not None:
                    q = q.filter(TestCase.project_id == pid)
                for r in q.all():
                    # 取步骤 expected 拼成期望说明；问答准确率用 title+preconditions 作问、steps expected 作答
                    steps = r.steps if isinstance(r.steps, list) else []
                    expects = []
                    for s in steps:
                        if isinstance(s, dict):
                            e = s.get("expected") or s.get("expected_result")
                            if e:
                                expects.append(str(e))
                    out.append({
                        "id": int(r.id),
                        "source_type": "testcase",
                        "name": str(r.title or f"TC-{r.id}"),
                        "input": str(r.title or "")
                        + (("\n" + str(r.preconditions or "")) if r.preconditions else ""),
                        "expected": "\n".join(expects) if expects else str(r.title or ""),
                    })
            except Exception:
                pass

        if badcase_ids:
            try:
                from models.orm import BadCase

                ids = [int(x) for x in badcase_ids if x is not None]
                q = db.session.query(BadCase).filter(BadCase.id.in_(ids))
                if pid is not None:
                    q = q.filter(BadCase.project_id == pid)
                for r in q.all():
                    out.append({
                        "id": int(r.id),
                        "source_type": "badcase",
                        "name": str(r.title or f"BC-{r.id}"),
                        "input": str(getattr(r, "answer", None) or r.title or ""),
                        "expected": str(
                            getattr(r, "correct_answer", None)
                            or getattr(r, "expected_result", None)
                            or ""
                        ),
                    })
            except Exception:
                pass
        return out

    async def _execute_test(self, test: Dict[str, Any], test_type: str, inp: str) -> Any:
        if test_type == "compare":
            return test.get("actual")

        if test_type == "functional":
            # 功能：若样本自带 actual 用它；否则用 LLM 根据 input 生成候选答案再比 expected
            if test.get("actual") is not None:
                return test.get("actual")
            return await self._llm_answer(str(inp or test.get("name") or ""))

        # conversation / default：调用模型回答问题
        return await self._llm_answer(str(inp))

    async def _llm_answer(self, question: str) -> str:
        q = (question or "").strip()
        if not q:
            return ""
        prompt = (
            "请直接回答下列测试问题，不要解释过程，答案尽量简洁准确：\n\n"
            f"{q}"
        )
        try:
            if hasattr(self.llm, "chat"):
                resp = self.llm.chat(prompt)
                if hasattr(resp, "__await__"):
                    resp = await resp
                return self._as_text(resp)
            if hasattr(self.llm, "parse_intent"):
                resp = self.llm.parse_intent(prompt)
                if hasattr(resp, "__await__"):
                    resp = await resp
                if isinstance(resp, dict):
                    return self._as_text(resp.get("answer") or resp.get("content") or resp)
                return self._as_text(resp)
        except Exception as e:
            return f"[llm_error] {e}"
        return ""

    async def _compare_results(
        self,
        actual: Any,
        expected: Any,
        *,
        use_llm_judge: bool = True,
        question: str = "",
    ) -> tuple[bool, float, str]:
        a = self._as_text(actual).strip()
        e = self._as_text(expected).strip()
        if not e and not a:
            return True, 1.0, "both_empty"
        if not e:
            return True, 1.0, "no_expected"
        if not a:
            return False, 0.0, "empty_actual"

        # 精确 / 包含
        if a == e:
            return True, 1.0, "exact"
        al, el = a.lower(), e.lower()
        if el in al or al in el:
            return True, 0.9, "contains"

        # token overlap
        overlap = self._token_overlap(al, el)
        if overlap >= 0.72:
            return True, overlap, "token_overlap"

        if use_llm_judge and self.llm is not None:
            judged = await self._llm_judge(question=question, expected=e, actual=a)
            if judged is not None:
                return judged

        return False, overlap, "mismatch"

    async def _llm_judge(
        self, *, question: str, expected: str, actual: str
    ) -> Optional[tuple[bool, float, str]]:
        prompt = (
            "你是测试评判员。判断 actual 是否在语义上答对了 expected。"
            "只输出 JSON：{\"pass\":true/false,\"score\":0到1,\"reason\":\"短原因\"}\n"
            f"question: {question[:500]}\n"
            f"expected: {expected[:800]}\n"
            f"actual: {actual[:800]}\n"
        )
        try:
            raw = ""
            if hasattr(self.llm, "chat"):
                resp = self.llm.chat(prompt)
                if hasattr(resp, "__await__"):
                    resp = await resp
                raw = self._as_text(resp)
            else:
                return None
            m = re.search(r"\{[\s\S]*\}", raw)
            if not m:
                return None
            data = json.loads(m.group(0))
            ok = bool(data.get("pass"))
            try:
                score = float(data.get("score", 1.0 if ok else 0.0))
            except (TypeError, ValueError):
                score = 1.0 if ok else 0.0
            reason = str(data.get("reason") or "llm_judge")
            return ok, max(0.0, min(1.0, score)), reason
        except Exception:
            return None

    @staticmethod
    def _token_overlap(a: str, b: str) -> float:
        def toks(s: str) -> set:
            parts = re.findall(r"[\w\u4e00-\u9fff]+", s)
            return {p for p in parts if len(p) > 1}

        ta, tb = toks(a), toks(b)
        if not ta or not tb:
            return 0.0
        inter = len(ta & tb)
        return inter / max(len(ta), len(tb))

    async def _compute_diff(self, expected: Any, actual: Any) -> Dict[str, Any]:
        e, a = self._as_text(expected), self._as_text(actual)
        return {
            "expected_preview": e[:200],
            "actual_preview": a[:200],
            "expected_length": len(e),
            "actual_length": len(a),
            "overlap": self._token_overlap(e.lower(), a.lower()),
        }

    @staticmethod
    def _as_text(v: Any) -> str:
        if v is None:
            return ""
        if isinstance(v, str):
            return v
        if isinstance(v, (dict, list)):
            try:
                return json.dumps(v, ensure_ascii=False)
            except Exception:
                return str(v)
        return str(v)
