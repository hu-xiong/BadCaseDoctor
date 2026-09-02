# -*- coding: utf-8 -*-
"""explore 模式：session/navigate/login 就绪后自动执行探测性测试。"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

from agents.cdp.test_intent import detect_browser_url_test_bootstrap, extract_http_url


def _build_explore_report(out: Dict[str, Any], *, url: str = "") -> str:
    """给人看的探测结论（中文），避免只剩一句 Exploratory test finished。"""
    err = str(out.get("error") or out.get("message") or "").strip()
    if out.get("success") is False and err and out.get("engine") != "midscene":
        return f"探测性测试失败：{err}"[:2000]

    # Midscene 结构化报告优先
    if str(out.get("engine") or "") == "midscene" or out.get("tested_flows") is not None:
        lines = ["Midscene 界面巡检已完成。"]
        page = out.get("page") if isinstance(out.get("page"), dict) else {}
        page_url = str((page or {}).get("url") or url or "").strip()
        title = str((page or {}).get("title") or "").strip()
        if page_url:
            lines.append(f"页面：{page_url}" + (f"（{title}）" if title else ""))
        tested = out.get("tested_flows") or []
        passed = out.get("passed") or []
        failed = out.get("failed") or []
        if isinstance(tested, list) and tested:
            lines.append("已测入口：" + "；".join(str(x) for x in tested[:10]))
        if isinstance(passed, list) and passed:
            lines.append("通过：" + "；".join(str(x) for x in passed[:10]))
        if isinstance(failed, list) and failed:
            lines.append("失败：")
            for i, item in enumerate(failed[:8]):
                if isinstance(item, dict):
                    lines.append(f"  {i + 1}. {item.get('step') or ''} — {item.get('reason') or ''}")
                else:
                    lines.append(f"  {i + 1}. {item}")
        base = str(out.get("summary") or "").strip()
        if base and base not in "\n".join(lines):
            lines.append(base[:800])
        report_file = str(out.get("midscene_report_file") or "").strip()
        if report_file:
            lines.append(f"报告文件：{report_file}")
        if out.get("success") is False and err and "Midscene" not in "\n".join(lines):
            lines.append(f"错误：{err[:400]}")
        return "\n".join(lines)[:2000]

    clicks = int(out.get("exploration_clicks") or out.get("click_count") or 0)
    fills = int(out.get("exploration_fills") or 0)
    elements = int(out.get("element_count") or 0)
    issues = out.get("exploration_issues") or out.get("issues") or []
    n_issues = len(issues) if isinstance(issues, list) else 0
    page = out.get("page") if isinstance(out.get("page"), dict) else {}
    page_url = str((page or {}).get("url") or url or "").strip()
    title = str((page or {}).get("title") or "").strip()
    base = str(out.get("summary") or "").strip()

    severe = [
        i
        for i in (issues if isinstance(issues, list) else [])
        if isinstance(i, dict)
        and str(i.get("type") or "") in ("error_url", "error_text", "error_title", "click_failed")
    ]
    soft = [
        i
        for i in (issues if isinstance(issues, list) else [])
        if isinstance(i, dict) and i not in severe
    ]

    lines = ["探测性测试已完成。"]
    if page_url:
        lines.append(f"页面：{page_url}" + (f"（{title}）" if title else ""))
    lines.append(f"可交互元素 {elements} 个，点击 {clicks} 次，填写 {fills} 次。")
    if severe:
        lines.append(f"明显问题 {len(severe)} 个：")
        for i, issue in enumerate(severe[:8]):
            msg = str(issue.get("message") or issue.get("type") or "")[:180]
            if msg:
                lines.append(f"  {i + 1}. {msg}")
    else:
        if elements <= 0 and clicks <= 0:
            lines.append("当前页几乎没有可点击控件，未能深入交互（页面可能仍在加载、未登录或内容为空）。")
        else:
            lines.append("未发现页面级报错（404/500/错误文案等）。")
    if soft:
        lines.append(
            f"另有 {len(soft)} 条低优先级交互探测失败（多为日期旋钮/下拉/弹层时序，不一定是产品缺陷）："
        )
        for i, issue in enumerate(soft[:5]):
            msg = str(issue.get("message") or issue.get("type") or "")[:120]
            if msg:
                lines.append(f"  · {msg}")
    if base and base not in "\n".join(lines) and "无法填写" not in base:
        lines.append(base[:400])
    return "\n".join(lines)[:2000]


def cdp_auto_run_explore_enabled() -> bool:
    return (os.getenv("CDP_AUTO_RUN_EXPLORE", "1") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def _get_cdp_tool(engine: Any) -> Any:
    tools = getattr(engine, "tools", None)
    if tools is None:
        return None
    if hasattr(tools, "get"):
        return tools.get("cdp")
    if isinstance(tools, dict):
        return tools.get("cdp")
    return None


def _should_auto_explore(
    *,
    user_input: str,
    result_context: Dict[str, Any],
) -> bool:
    if result_context.get("_cdp_force_auto_explore"):
        return True
    run = result_context.get("cdp_test_run")
    if isinstance(run, dict) and str(run.get("mode") or "").lower() == "explore":
        return True
    if detect_browser_url_test_bootstrap(user_input):
        return True
    text = user_input or ""
    if extract_http_url(text) and any(k in text for k in ("测试", "探测", "探索", "explore", "测一下", "测试下")):
        return True
    if any(k in text for k in ("探测性", "探索性", "探测一下", "探索一下", "explore")):
        return True
    return False


async def maybe_auto_run_explore(
    engine: Any,
    observation: Dict[str, Any],
    *,
    action: str = "",
    params: Optional[Dict[str, Any]] = None,
    project_id: Optional[int] = None,
    plan_id: Optional[int] = None,
    user_query: str = "",
    result_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    session/navigate/login 成功后，若用户意图为测站/探测，自动跑 cdp explore phase=full
    （默认 Midscene 巡检，见 CDP_EXPLORE_ENGINE）。
    """
    if not isinstance(observation, dict):
        return observation
    if not cdp_auto_run_explore_enabled():
        return observation
    if not isinstance(result_context, dict):
        return observation
    if result_context.get("_cdp_explore_auto_ran"):
        return observation

    act = (action or observation.get("action") or "").strip().lower()
    # session.create 观测里常带 action=create
    if act == "create" and (
        observation.get("session_id")
        or str((params or {}).get("action") or "").lower() == "session"
    ):
        act = "session"
    if act in ("explore",):
        result_context["_cdp_explore_auto_ran"] = True
        return observation
    if act not in ("session", "navigate", "login", "open", "focus", "create"):
        print(f"[CDP] auto explore skip: unsupported action={act!r}", flush=True)
        return observation
    if observation.get("success") is False:
        print("[CDP] auto explore skip: prior step failed", flush=True)
        return observation
    # 等用户填验证码时不探测；纯登录失败仍可对当前页探测
    if observation.get("await_verification_code"):
        print("[CDP] auto explore skip: await_verification_code", flush=True)
        return observation

    user_input = (user_query or "").strip()
    if not _should_auto_explore(user_input=user_input, result_context=result_context):
        print(
            f"[CDP] auto explore skip: intent not matched q={user_input[:80]!r}",
            flush=True,
        )
        return observation

    tool = _get_cdp_tool(engine)
    if tool is None or not hasattr(tool, "execute"):
        # LangGraph 引擎偶发 tools 在 helpers 上
        helpers = getattr(engine, "helpers", None)
        if helpers is not None:
            tool = _get_cdp_tool(helpers)
    if tool is None or not hasattr(tool, "execute"):
        observation["cdp_auto_explore_skipped"] = "no_cdp_tool"
        print("[CDP] auto explore skip: no_cdp_tool", flush=True)
        return observation

    sid = (
        observation.get("session_id")
        or (params or {}).get("session_id")
        or result_context.get("cdp_session_id")
    )
    if sid:
        result_context["cdp_session_id"] = sid
    if not sid:
        observation["cdp_auto_explore_skipped"] = "no_session_id"
        return observation

    result_context["_cdp_explore_auto_ran"] = True
    url = (
        extract_http_url(user_input)
        or (params or {}).get("url")
        or result_context.get("cdp_target_url")
    )
    uid = (
        getattr(engine, "user_id", None)
        or getattr(engine, "_user_id", None)
        or (params or {}).get("user_id")
        or result_context.get("user_id")
    )
    call_kw: Dict[str, Any] = {
        "action": "explore",
        "phase": "full",
        "session_id": sid,
        "user_query": user_input,
        "natural_query": user_input,
        "result_context": result_context,
    }
    if project_id is not None:
        call_kw["project_id"] = project_id
    if plan_id is not None:
        call_kw["plan_id"] = plan_id
    if uid is not None and str(uid).strip():
        call_kw["user_id"] = uid
    if url:
        call_kw["url"] = url
        result_context["cdp_target_url"] = url

    # 目标不是登录页时：若当前停在登录页，先登录再回目标页，再探测
    login_note = ""
    try:
        from agents.cdp.login_flow import is_login_url

        target_is_login = bool(url and is_login_url(url))
        auto_login = (
            observation.get("auto_login")
            if isinstance(observation.get("auto_login"), dict)
            else {}
        )
        already_logged_in = bool(auto_login.get("login_success"))
        if (not target_is_login) and project_id is not None and not already_logged_in:
            page_url = ""
            try:
                snap0 = await tool.execute(
                    action="snapshot",
                    session_id=sid,
                    user_id=uid,
                    project_id=project_id,
                )
                page_url = str(
                    ((snap0.get("page") or {}) if isinstance(snap0.get("page"), dict) else {}).get(
                        "url"
                    )
                    or snap0.get("url")
                    or ""
                )
            except Exception:
                page_url = ""
            if (not page_url) or is_login_url(page_url):
                print(
                    f"[CDP] auto explore: login then navigate url={url!r} from={page_url!r}",
                    flush=True,
                )
                login_out = await tool.execute(
                    action="login",
                    session_id=sid,
                    project_id=project_id,
                    user_id=uid,
                    return_url=url,
                    result_context=result_context,
                )
                _login_ok = bool(
                    isinstance(login_out, dict)
                    and (login_out.get("login_success") or login_out.get("success"))
                )
                observation["cdp_auto_login_before_explore"] = {
                    "success": _login_ok,
                    "page": (login_out or {}).get("page") if isinstance(login_out, dict) else None,
                    "error": (
                        (login_out or {}).get("error") or (login_out or {}).get("message")
                        if isinstance(login_out, dict)
                        else None
                    ),
                }
                if _login_ok:
                    login_note = "已自动登录并进入目标页。"
                    if url:
                        nav = await tool.execute(
                            action="navigate",
                            session_id=sid,
                            url=url,
                            user_id=uid,
                            project_id=project_id,
                        )
                        observation["cdp_auto_nav_before_explore"] = {
                            "success": bool(isinstance(nav, dict) and nav.get("success")),
                            "page": (nav or {}).get("page") if isinstance(nav, dict) else None,
                        }
                elif isinstance(login_out, dict) and (
                    login_out.get("await_verification_code")
                    or login_out.get("await_user_credentials")
                ):
                    observation["cdp_auto_explore_skipped"] = "await_login"
                    observation["summary"] = str(
                        login_out.get("message") or "需要登录凭证/验证码后才能继续探测。"
                    )
                    result_context["_cdp_explore_auto_ran"] = False
                    print("[CDP] auto explore paused: await login/verification", flush=True)
                    return observation
    except Exception as _login_ex:
        print(f"[CDP] auto explore pre-login skipped: {_login_ex}", flush=True)

    print(
        f"[CDP] auto explore start sid={sid} url={url or ''} user_id={uid!r}",
        flush=True,
    )
    try:
        out = await tool.execute(**call_kw)
    except Exception as e:
        out = {"success": False, "error": str(e), "action": "explore"}

    if not isinstance(out, dict):
        out = {"success": False, "error": "invalid explore result", "action": "explore"}

    report = _build_explore_report(out, url=url or "")
    if login_note and login_note not in report:
        report = f"{login_note}\n{report}"
    observation["cdp_auto_explore"] = {
        "ran": True,
        "success": bool(out.get("success")),
        "summary": report,
        "error": out.get("error") or out.get("message"),
        "issues": out.get("exploration_issues") or out.get("issues"),
        "clicks": out.get("exploration_clicks") or out.get("click_count"),
        "fills": out.get("exploration_fills"),
        "element_count": out.get("element_count"),
    }
    # 把探测结果合并进主 observation，便于后续总结/建 Bug
    for k in (
        "exploration_issues",
        "issues",
        "element_inventory",
        "cdp_test_evidence",
        "assertion_failed",
        "has_obvious_issues",
        "steps",
        "screenshot_url",
        "page",
        "exploration_clicks",
        "exploration_fills",
        "element_count",
        "error",
        "message",
    ):
        if k in out and out[k] is not None:
            observation[k] = out[k]
    observation["summary"] = report
    observation["explore_success"] = bool(out.get("success"))
    if out.get("success") is False:
        print(
            f"[CDP] auto explore failed: {out.get('error') or out.get('message') or out}",
            flush=True,
        )

    try:
        from agents.cdp.test_task import (
            get_active_run_id,
            record_cdp_test_task_step,
            finalize_cdp_test_task,
        )

        run_id = get_active_run_id(result_context)
        if run_id:
            record_cdp_test_task_step(
                engine,
                run_id,
                action="explore",
                params={"phase": "full", "url": url},
                observation=out,
                result_context=result_context,
                finalize=True,
            )
            final = finalize_cdp_test_task(engine, run_id, result_context=result_context)
            if final:
                observation["cdp_test_run"] = final
    except Exception as _rec_ex:
        print(f"[CDP] auto explore record skipped: {_rec_ex}", flush=True)

    print(
        f"[CDP] auto explore done success={observation.get('explore_success')} "
        f"issues={len(observation.get('exploration_issues') or [])}",
        flush=True,
    )
    return observation
