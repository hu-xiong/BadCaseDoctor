# -*- coding: utf-8 -*-
"""将测试用例自然语言 steps 解析并驱动 CDP（click/fill/navigate/assert）。"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse


def _norm_step_fields(raw: Any) -> Tuple[str, str]:
    """兼容 {step, expected} / {description, expected_result} / 纯字符串。"""
    if isinstance(raw, str):
        return raw.strip(), ""
    if not isinstance(raw, dict):
        return "", ""
    step = str(
        raw.get("step")
        or raw.get("description")
        or raw.get("action")
        or raw.get("desc")
        or ""
    ).strip()
    expected = str(
        raw.get("expected")
        or raw.get("expected_result")
        or raw.get("expect")
        or ""
    ).strip()
    return step, expected


def parse_nl_step(step_text: str, expected: str = "") -> Dict[str, Any]:
    """
    启发式解析一步自然语言操作。
    返回: {kind, url?, target?, value?, text_contains?}
    kind: navigate|click|fill|wait|assert|login|unknown
    """
    text = (step_text or "").strip()
    exp = (expected or "").strip()
    low = text.lower()
    out: Dict[str, Any] = {"kind": "unknown", "raw": text, "expected": exp}

    # URL
    m_url = re.search(r"https?://[^\s\"'<>]+", text)
    if m_url and any(k in text for k in ("打开", "访问", "进入", "跳转", "navigate", "open", "go to", "前往")):
        out["kind"] = "navigate"
        out["url"] = m_url.group(0).rstrip(".,;，。")
        return out
    if m_url and (text.startswith("http") or "url" in low):
        out["kind"] = "navigate"
        out["url"] = m_url.group(0).rstrip(".,;，。")
        return out

    # 「点击登录」优先 click；整页登录流程才用 login
    if any(k in text for k in ("登录", "登陆", "login", "签入")) and not any(
        k in text for k in ("点击", "单击", "输入", "填写", "click")
    ):
        out["kind"] = "login"
        return out

    # fill: 在…输入… / 输入用户名 xxx
    m_fill = re.search(
        r"(?:在|向|往)?[「\"'【\[]?([^「\"'】\]，,。]{1,40}?)[」\"'】\]]?"
        r"(?:中|里|内)?(?:输入|填写|填入|键入)\s*[「\"']?(.+?)[」\"']?\s*$",
        text,
    )
    if m_fill:
        out["kind"] = "fill"
        out["target"] = m_fill.group(1).strip()
        out["value"] = m_fill.group(2).strip().strip("「」\"'")
        return out
    m_fill2 = re.search(
        r"(?:输入|填写|填入|键入)\s*[「\"']?(.+?)[」\"']?\s*(?:到|至|入)?\s*"
        r"[「\"']?([^「\"'，,。]{1,40})[」\"']?",
        text,
    )
    if m_fill2 and any(k in text for k in ("输入", "填写", "填入", "键入")):
        # 「输入 xxx」可能只有 value
        g1, g2 = m_fill2.group(1).strip(), m_fill2.group(2).strip()
        if any(k in g2 for k in ("框", "栏", "字段", "账号", "密码", "用户名", "邮箱", "input", "password")):
            out["kind"] = "fill"
            out["value"] = g1
            out["target"] = g2
            return out
        out["kind"] = "fill"
        out["value"] = g1
        out["target"] = g2 if g2 != g1 else ""
        return out
    if re.match(r"^(输入|填写|填入|键入)\s+\S+", text):
        out["kind"] = "fill"
        out["value"] = re.sub(r"^(输入|填写|填入|键入)\s+", "", text).strip().strip("「」\"'")
        out["target"] = ""
        return out

    # click
    if any(k in text for k in ("点击", "单击", "按下", "点一下", "click", "tap")):
        out["kind"] = "click"
        m = re.search(
            r"(?:点击|单击|按下|点一下|click|tap)\s*[「\"'【\[]?(.+?)[」\"'】\]]?\s*$",
            text,
            re.I,
        )
        if m:
            out["target"] = m.group(1).strip().rstrip("按钮。.,，")
        else:
            out["target"] = re.sub(
                r"^(请)?(点击|单击|按下|点一下|click|tap)\s*", "", text, flags=re.I
            ).strip()
        return out

    if any(k in text for k in ("等待", "稍等", "wait")):
        out["kind"] = "wait"
        m = re.search(r"(\d+)\s*(秒|s|ms)?", text)
        if m:
            n = int(m.group(1))
            unit = (m.group(2) or "秒").lower()
            out["timeout_ms"] = n if unit == "ms" else n * 1000
        else:
            out["timeout_ms"] = 2000
        return out

    if any(k in text for k in ("验证", "检查", "确认", "应看到", "应该", "assert", "expect")):
        out["kind"] = "assert"
        out["text_contains"] = exp or _extract_assert_text(text)
        return out

    # 仅 expected → 本步做完后 assert
    if exp and not text:
        out["kind"] = "assert"
        out["text_contains"] = exp
        return out

    # 默认：有文案则尝试 click，再靠 expected assert
    if text:
        out["kind"] = "click"
        out["target"] = text[:60]
    return out


def _extract_assert_text(text: str) -> str:
    m = re.search(
        r"(?:验证|检查|确认|应看到|应该显示|看到|出现)\s*[「\"']?(.+?)[」\"']?\s*$",
        text,
    )
    if m:
        return m.group(1).strip()
    return re.sub(r"^(验证|检查|确认|断言)\s*", "", text).strip()


def find_ref_by_name(
    nodes: List[Dict[str, Any]],
    target: str,
    *,
    prefer_roles: Optional[List[str]] = None,
) -> Optional[str]:
    """在 snapshot nodes 中按 name/近似匹配找 ref。"""
    t = (target or "").strip()
    if not t or not nodes:
        return None
    prefer = [r.lower() for r in (prefer_roles or [])]
    t_low = t.lower()

    def score(n: Dict[str, Any]) -> int:
        name = str(n.get("name") or "").strip()
        role = str(n.get("role") or "").lower()
        if not name:
            return -1
        s = 0
        if name == t or name.lower() == t_low:
            s = 100
        elif t in name or name in t:
            s = 80
        elif t_low in name.lower() or name.lower() in t_low:
            s = 60
        else:
            return -1
        if prefer and role in prefer:
            s += 15
        if role in ("button", "link", "textbox", "searchbox", "combobox"):
            s += 5
        return s

    best = None
    best_s = -1
    for n in nodes:
        sc = score(n)
        if sc > best_s:
            best_s = sc
            best = n
    if best and best_s >= 60:
        ref = best.get("ref")
        return str(ref) if ref else None
    return None


def find_fill_target(nodes: List[Dict[str, Any]], target: str, value: str) -> Optional[str]:
    prefer = ["textbox", "searchbox", "combobox", "spinbutton"]
    if target:
        ref = find_ref_by_name(nodes, target, prefer_roles=prefer)
        if ref:
            return ref
    # 密码启发式
    if any(k in (target + value) for k in ("密码", "password", "pwd")):
        for n in nodes:
            role = str(n.get("role") or "").lower()
            name = str(n.get("name") or "").lower()
            if role == "textbox" and ("pass" in name or "密码" in name):
                return str(n.get("ref") or "") or None
    # 取第一个可编辑框
    for n in nodes:
        if str(n.get("role") or "").lower() in ("textbox", "searchbox"):
            ref = n.get("ref")
            if ref:
                return str(ref)
    return None


async def execute_parsed_step(
    cdp_tool: Any,
    parsed: Dict[str, Any],
    *,
    session_id: Optional[str] = None,
    owner_kwargs: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """按 parse_nl_step 结果调用 CdpTool。"""
    kw = dict(owner_kwargs or {})
    if session_id:
        kw["session_id"] = session_id
    kind = parsed.get("kind") or "unknown"

    if kind == "navigate":
        url = parsed.get("url")
        if not url:
            return {"success": False, "error": "navigate 缺少 url", "parsed": parsed}
        # 确保有 session
        if not kw.get("session_id"):
            sess = await cdp_tool.execute(action="session", url=url, **kw)
            if not sess.get("success"):
                return {**sess, "parsed": parsed}
            kw["session_id"] = sess.get("session_id")
            return {**sess, "parsed": parsed, "step_kind": "navigate"}
        return {
            **(await cdp_tool.execute(action="navigate", url=url, **kw)),
            "parsed": parsed,
            "step_kind": "navigate",
        }

    if kind == "login":
        return {
            **(await cdp_tool.execute(action="login", **kw)),
            "parsed": parsed,
            "step_kind": "login",
        }

    if kind == "wait":
        return {
            **(
                await cdp_tool.execute(
                    action="wait",
                    timeout_ms=parsed.get("timeout_ms") or 2000,
                    **kw,
                )
            ),
            "parsed": parsed,
            "step_kind": "wait",
        }

    # 需要 snapshot
    snap = await cdp_tool.execute(action="snapshot", scope="interactive", **kw)
    if not snap.get("success"):
        return {**snap, "parsed": parsed}
    nodes = snap.get("nodes") or []
    kw["session_id"] = kw.get("session_id") or snap.get("session_id")
    kw["snapshot_id"] = snap.get("snapshot_id")

    if kind == "click":
        target = str(parsed.get("target") or "")
        ref = find_ref_by_name(nodes, target, prefer_roles=["button", "link", "tab", "menuitem"])
        if not ref:
            return {
                "success": False,
                "error": f"未在页面找到可点击目标「{target}」",
                "parsed": parsed,
                "step_kind": "click",
                "session_id": kw.get("session_id"),
            }
        out = await cdp_tool.execute(action="click", ref=ref, **kw)
        out["parsed"] = parsed
        out["step_kind"] = "click"
        out["ref"] = ref
        return out

    if kind == "fill":
        target = str(parsed.get("target") or "")
        value = str(parsed.get("value") or "")
        if not value:
            return {"success": False, "error": "fill 缺少输入值", "parsed": parsed}
        ref = find_fill_target(nodes, target, value)
        if not ref:
            return {
                "success": False,
                "error": f"未找到输入框「{target or '默认'}」",
                "parsed": parsed,
                "step_kind": "fill",
            }
        out = await cdp_tool.execute(action="fill", ref=ref, text=value, **kw)
        out["parsed"] = parsed
        out["step_kind"] = "fill"
        out["ref"] = ref
        return out

    if kind == "assert":
        text_contains = (parsed.get("text_contains") or parsed.get("expected") or "").strip()
        if not text_contains:
            return {"success": True, "skipped": True, "reason": "无断言文本", "parsed": parsed}
        out = await cdp_tool.execute(
            action="assert", text_contains=text_contains, **kw
        )
        out["parsed"] = parsed
        out["step_kind"] = "assert"
        return out

    return {
        "success": False,
        "error": f"无法解析步骤: {parsed.get('raw', '')[:80]}",
        "parsed": parsed,
        "step_kind": "unknown",
    }


async def run_testcase_step(
    cdp_tool: Any,
    *,
    step: Any = None,
    step_text: str = "",
    expected: str = "",
    session_id: Optional[str] = None,
    assert_expected: bool = True,
    owner_kwargs: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """执行单条用例步骤；成功后按 expected 做 text_contains 断言。"""
    st, exp = _norm_step_fields(step) if step is not None else (step_text, expected)
    if not st and exp:
        st = ""
    if not st and not exp:
        return {"success": False, "error": "步骤为空"}

    parsed = parse_nl_step(st, exp)
    act_out = await execute_parsed_step(
        cdp_tool, parsed, session_id=session_id, owner_kwargs=owner_kwargs
    )
    sid = act_out.get("session_id") or session_id or (owner_kwargs or {}).get("session_id")

    # 操作类步骤成功后，用 expected 做收尾断言
    if (
        assert_expected
        and exp
        and act_out.get("success")
        and parsed.get("kind") not in ("assert",)
    ):
        assert_out = await cdp_tool.execute(
            action="assert",
            text_contains=exp,
            session_id=sid,
            **{k: v for k, v in (owner_kwargs or {}).items() if k != "session_id"},
        )
        return {
            "success": bool(assert_out.get("success")),
            "step_action": act_out,
            "step_assert": assert_out,
            "parsed": parsed,
            "session_id": sid,
            "expected": exp,
            "assertion_failed": not bool(assert_out.get("success")),
            "summary": f"{parsed.get('kind')}: {(st or '')[:60]}"
            + (f" → expect「{exp[:40]}」" + ("✓" if assert_out.get("success") else "✗")),
        }

    act_out.setdefault(
        "summary",
        f"{parsed.get('kind')}: {(st or exp or '')[:80]}",
    )
    act_out["session_id"] = sid
    return act_out


async def run_testcase_steps(
    cdp_tool: Any,
    steps: List[Any],
    *,
    session_id: Optional[str] = None,
    stop_on_fail: bool = True,
    owner_kwargs: Optional[Dict[str, Any]] = None,
    testcase_id: Optional[int] = None,
) -> Dict[str, Any]:
    """顺序执行用例全部 steps。"""
    results: List[Dict[str, Any]] = []
    sid = session_id
    passed = failed = 0
    for i, raw in enumerate(steps or []):
        one = await run_testcase_step(
            cdp_tool,
            step=raw,
            session_id=sid,
            owner_kwargs=owner_kwargs,
        )
        sid = one.get("session_id") or sid
        one["step_index"] = i
        if testcase_id is not None:
            one["testcase_id"] = testcase_id
        results.append(one)
        ok = one.get("success") is True and not one.get("assertion_failed")
        if ok:
            passed += 1
        else:
            failed += 1
            if stop_on_fail:
                break
    return {
        "success": failed == 0 and passed > 0,
        "tool": "cdp_run_testcase",
        "session_id": sid,
        "testcase_id": testcase_id,
        "pass_count": passed,
        "fail_count": failed,
        "steps_run": len(results),
        "results": results,
        "summary": f"用例步骤 {passed} 通过 / {failed} 失败（共执行 {len(results)}）",
    }


def looks_like_url(s: str) -> bool:
    try:
        p = urlparse(s)
        return bool(p.scheme and p.netloc)
    except Exception:
        return False
