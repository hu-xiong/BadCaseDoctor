# -*- coding: utf-8 -*-
"""explore 模式：session/navigate/login 就绪后自动执行探测性测试。"""

from __future__ import annotations

import asyncio
import os
import time
from typing import Any, Dict, List, Optional

from agents.cdp.test_intent import detect_browser_url_test_bootstrap, extract_http_url


def _build_explore_report(out: Dict[str, Any], *, url: str = "") -> str:
    """给人看的探测结论（中文），避免只剩一句 Exploratory test finished。"""
    err = str(out.get("error") or out.get("message") or "").strip()
    # 仅当没有结构化台账（tested_flows 字段）时才退化为一句失败结论；
    # 有台账时走下方结构化分支，保留已测/通过/失败明细与准确原因
    if (
        out.get("success") is False
        and err
        and out.get("engine") != "midscene"
        and out.get("tested_flows") is None
    ):
        return f"探测性测试失败：{err}"[:2000]

    # Midscene 结构化报告优先
    if str(out.get("engine") or "") == "midscene" or out.get("tested_flows") is not None:
        # 撞登录墙暂停时 success 可能仍为 True（巡检本身未失败），但结论不能写「已完成」：
        # 首行必须明确未完成，与后续「⏸ 已暂停」保持一致
        _paused = bool(out.get("await_manual_login"))
        ok = out.get("success") is not False and not _paused
        lines = ["Midscene 界面巡检已完成。" if ok else "Midscene 界面巡检未完成。"]
        if _paused:
            lines.append("原因：页面被登录拦截，需要你先完成登录。")
        _lr = out.get("login_recover") if isinstance(out.get("login_recover"), dict) else {}
        if _lr.get("blocked_round1") and _lr.get("note"):
            lines.append(str(_lr["note"]))
        if out.get("await_manual_login"):
            _pause = str(out.get("error") or out.get("message") or "").strip()
            if _pause:
                lines.append(_pause if _pause.startswith("⏸") else f"⏸ {_pause}")
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
        if base:
            # 逐行去重：mapper 的 summary 与本段头部同构（"未完成。"、"页面：xxx"），
            # 整段追加会造成这两行重复出现
            existing = "\n".join(lines)
            for _ln in base[:800].splitlines():
                _s = _ln.strip()
                if _s and _s not in existing:
                    lines.append(_ln)
                    existing += "\n" + _ln
        report_file = str(out.get("midscene_report_file") or "").strip()
        if report_file:
            lines.append(f"报告文件：{report_file}")
        if out.get("success") is False and err and err[:80] not in "\n".join(lines):
            lines.append(f"原因：{err[:500]}")
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


def _explore_login_wait_sec() -> int:
    """人工登录等待窗口秒数（CDP_EXPLORE_LOGIN_WAIT_SEC，默认 60s；0=检测到登录墙立即暂停；30~600 夹取）。"""
    try:
        v = int((os.getenv("CDP_EXPLORE_LOGIN_WAIT_SEC") or "60").strip())
    except (TypeError, ValueError):
        v = 60
    if v <= 0:
        return 0
    return max(30, min(v, 600))


async def _cdp_probe_page(
    tool: Any, sid: str, uid: Any, project_id: Optional[int]
) -> Dict[str, Any]:
    """当前页快照探针：同一次 snapshot 同时取 url 与交互元素（供登录完成检测复用）。"""
    try:
        snap = await tool.execute(
            action="snapshot", session_id=sid, user_id=uid, project_id=project_id
        )
        if not isinstance(snap, dict):
            return {}
        page = snap.get("page") if isinstance(snap.get("page"), dict) else {}
        nodes = snap.get("nodes")
        return {
            "url": str((page or {}).get("url") or snap.get("url") or ""),
            "nodes": nodes if isinstance(nodes, list) else [],
        }
    except Exception:
        return {}


async def _cdp_current_page_url(
    tool: Any, sid: str, uid: Any, project_id: Optional[int]
) -> str:
    return str((await _cdp_probe_page(tool, sid, uid, project_id)).get("url") or "")


_LOGIN_FIELD_ROLES = frozenset({
    "textbox",
    "searchbox",
    "combobox",
    "spinbutton",
})


def _login_form_gone(nodes: List[Dict[str, Any]]) -> bool:
    """登录页 URL 下，页面已无账号/密码/验证码输入框 → 视为已登录。

    覆盖 SPA 站点登录成功后 URL hash 不变（仍停在 #/login）的场景。
    只认输入类元素（textbox 等），避免已登录页面里「修改密码」这类链接文本造成误判。
    """
    if not nodes:
        return False
    try:
        from agents.cdp.login_flow import (
            _CODE_HINTS,
            _PASSWORD_HINTS,
            _USERNAME_HINTS,
        )
    except Exception:
        return False
    for n in nodes:
        if not isinstance(n, dict):
            continue
        role = str(n.get("role") or "").strip().lower()
        if role not in _LOGIN_FIELD_ROLES:
            continue
        text = f"{n.get('name') or ''} {n.get('value') or ''}".strip()
        if (
            _PASSWORD_HINTS.search(text)
            or _CODE_HINTS.search(text)
            or _USERNAME_HINTS.search(text)
        ):
            return False
    return True


def _detect_login_block(out: Dict[str, Any], page_url: str) -> bool:
    """判定巡检是否被登录阻塞：页面停在登录页（强信号）或报告明确说明被登录阻塞（文本兜底）。"""
    from agents.cdp.login_flow import is_login_url

    txt_parts = [str(out.get("summary") or ""), str(out.get("error") or "")]
    for item in (out.get("failed") or [])[:8]:
        txt_parts.append(str(item.get("step") if isinstance(item, dict) else item))
        txt_parts.append(str(item.get("reason") if isinstance(item, dict) else ""))
    txt = " ".join(txt_parts)
    if page_url and is_login_url(page_url):
        # SPA 登录后 URL hash 可能仍停在 #/login：本轮巡检实际成功且无登录相关失败记录时，视为未阻塞，
        # 避免白白多跑一轮恢复重跑（tgb.cn 这类站点登录后 hash 不变）
        has_ledger = bool(out.get("tested_flows") or out.get("passed"))
        if out.get("success") is not False and has_ledger and "登录" not in txt:
            return False
        return True
    if "登录" not in txt:
        return False
    return any(
        k in txt
        for k in ("无法登录", "被登录阻塞", "登录阻塞", "跳转至登录", "跳转到登录", "需要登录才")
    )


def _merge_explore_outputs(
    out1: Dict[str, Any], out2: Dict[str, Any], *, via: str = ""
) -> Dict[str, Any]:
    """登录恢复后两轮巡检结果合并：台账去重、以第二轮为最新事实。

    via：登录解除方式（auto=配置账密自动登录；manual=用户人工登录）。
    """

    def _uniq(*lists: Any) -> list:
        seen, merged = set(), []
        for lst in lists:
            if not isinstance(lst, list):
                continue
            for item in lst:
                key = str(item)[:300]
                if key not in seen:
                    seen.add(key)
                    merged.append(item)
        return merged

    merged: Dict[str, Any] = dict(out2)
    merged["tested_flows"] = _uniq(out1.get("tested_flows"), out2.get("tested_flows"))
    merged["passed"] = _uniq(out1.get("passed"), out2.get("passed"))
    ok2 = out2.get("success") is not False
    has_ledger2 = bool(merged["tested_flows"])
    if ok2 and has_ledger2:
        # 第二轮是登录后的完整巡检：失败项以第二轮为准（第一轮的「需登录」失败已被覆盖）
        merged["failed"] = list(out2.get("failed") or [])
        merged["exploration_issues"] = list(out2.get("exploration_issues") or [])
    else:
        merged["failed"] = _uniq(out1.get("failed"), out2.get("failed"))
        merged["exploration_issues"] = _uniq(
            out1.get("exploration_issues"), out2.get("exploration_issues")
        )
    merged["issues_found"] = len(merged["exploration_issues"])
    merged["has_blocking_bug"] = bool(
        out1.get("has_blocking_bug") or out2.get("has_blocking_bug")
    )
    merged["has_obvious_issues"] = bool(
        out1.get("has_obvious_issues") or out2.get("has_obvious_issues")
    )
    try:
        merged["element_count"] = int(out1.get("element_count") or 0) + int(
            out2.get("element_count") or 0
        )
    except (TypeError, ValueError):
        pass
    merged["execution_steps"] = list(out1.get("execution_steps") or []) + list(
        out2.get("execution_steps") or []
    )
    merged["midscene_action_steps"] = list(
        out1.get("midscene_action_steps") or []
    ) + list(out2.get("midscene_action_steps") or [])
    s2 = str(out2.get("summary") or "").strip()
    s1 = str(out1.get("summary") or "").strip()
    merged["summary"] = s2 or s1
    merged["success"] = ok2
    if ok2:
        merged["error"] = out2.get("error")
        merged["message"] = str(out2.get("message") or merged["summary"])[:500]
    # 第一轮结果作为历史保留，便于排查；note 会进最终报告，澄清登录是谁完成的
    merged["login_recover"] = {
        "blocked_round1": True,
        "via": "auto" if via == "auto" else "manual",
        "round1_summary": s1[:500],
        "round1_tested": list(out1.get("tested_flows") or []),
        "note": (
            "登录说明：首轮巡检因登录拦截中断，系统已用项目「网站登录配置」中的账号密码自动登录，"
            "随后完成了第二轮完整巡检。"
            if via == "auto"
            else "登录说明：首轮巡检因登录拦截中断，登录由你（用户）在浏览器中手动完成，"
            "系统检测到后自动继续并完成了第二轮巡检。"
        ),
    }
    return merged


async def _recover_from_login_block(
    tool: Any,
    out: Dict[str, Any],
    *,
    sid: str,
    uid: Any,
    project_id: Optional[int],
    target_url: str,
    user_input: str,
    result_context: Dict[str, Any],
    progress_queue: Any,
    chat_session_id: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    """巡检被登录阻塞时的恢复：优先自动登录（项目登录配置，密码不经 LLM）；
    否则等待人工在浏览器中完成登录（轮询检测，最长 CDP_EXPLORE_LOGIN_WAIT_SEC）；
    登录解决后重跑一轮巡检并合并结果。

    返回：恢复后的合并结果；未触发恢复返回 None。
    """
    from agents.cdp.login_flow import is_login_url
    from agents.cdp.midscene_bridge import CDP_TEXT_PROGRESS_PREFIX, _push_cdp_progress

    page_url = await _cdp_current_page_url(tool, sid, uid, project_id)
    if not _detect_login_block(out, page_url):
        return None

    print(f"[CDP] explore login-blocked detected page={page_url!r}", flush=True)
    _push_cdp_progress(
        progress_queue,
        CDP_TEXT_PROGRESS_PREFIX,
        "检测到登录拦截：先尝试用项目配置的账号自动登录…",
    )

    # 1) 自动登录：项目「网站登录配置」有账密则自动填表（不经过 LLM）
    login_ok = False
    login_out: Dict[str, Any] = {}
    try:
        login_out = await tool.execute(
            action="login",
            session_id=sid,
            project_id=project_id,
            user_id=uid,
            return_url=target_url,
            result_context=result_context,
        )
    except Exception as ex:
        login_out = {"success": False, "error": str(ex)}
    login_skipped = bool(isinstance(login_out, dict) and login_out.get("login_skipped"))
    if isinstance(login_out, dict) and login_out.get("login_success"):
        login_ok = True
        print("[CDP] explore login-recover: auto login ok", flush=True)
        _push_cdp_progress(
            progress_queue,
            CDP_TEXT_PROGRESS_PREFIX,
            "✅ 已用登录配置的账号自动登录成功，继续巡检…",
        )
    elif login_skipped:
        # 页面已非登录页/识别不到登录表单（多为等待期间用户已登录成功）：无需等待，直接重跑
        login_ok = True
        print("[CDP] explore login-recover: page not login, skip wait", flush=True)
        _push_cdp_progress(
            progress_queue,
            CDP_TEXT_PROGRESS_PREFIX,
            "✅ 检测到页面已可访问（登录已完成），继续巡检…",
        )

    # 2) 人工登录等待：浏览器停留在登录页等用户完成登录（轮询检测，不刷屏倒计时）
    recover_via = ""
    if login_ok:
        recover_via = "manual" if login_skipped else "auto"
    why = ""
    if not login_ok and isinstance(login_out, dict):
        if login_out.get("await_verification_code"):
            why = "该站登录需要验证码"
        elif login_out.get("await_user_credentials"):
            why = "项目未配置可用账号密码"
    if not login_ok:
        wait_sec = _explore_login_wait_sec()
        # 把浏览器带到前台，用户能直接看到登录页去操作
        try:
            await tool.execute(action="focus", session_id=sid, user_id=uid)
        except Exception:
            pass
        if wait_sec > 0:
            _tip = (
                f"⏳ 需要你手动登录（{why or '登录需人工完成'}）：浏览器已停留在登录页，"
                f"请完成登录，我会自动继续巡检（最多等待 {wait_sec}s，超时自动暂停，"
                "之后回复「登录好了」即可续跑）。"
            )
        else:
            _tip = (
                f"⏳ 需要你手动登录（{why or '登录需人工完成'}）：浏览器已停留在登录页，"
                "完成登录后回复「登录好了」（或「继续」），我会接着完成巡检。"
            )
        _push_cdp_progress(progress_queue, CDP_TEXT_PROGRESS_PREFIX, _tip)
        start_url = page_url
        seen_login_page = bool(page_url) and is_login_url(page_url)
        deadline = time.time() + wait_sec
        last_log = time.time()
        form_gone_streak = 0
        while time.time() < deadline:
            await asyncio.sleep(3)
            probe = await _cdp_probe_page(tool, sid, uid, project_id)
            cur = str(probe.get("url") or "")
            if not cur:
                continue
            if is_login_url(cur):
                seen_login_page = True
                # SPA 常见：登录成功后 URL hash 仍停在 #/login，仅看 URL 会永远等下去。
                # 页面元素判据：连续 2 次快照中登录表单（账号/密码/验证码输入框）均消失 → 视为已完成登录
                if _login_form_gone(probe.get("nodes") or []):
                    form_gone_streak += 1
                else:
                    form_gone_streak = 0
                if form_gone_streak >= 2:
                    login_ok = True
                    recover_via = "manual"
                    print(
                        "[CDP] explore login-recover: login form gone (url still login), "
                        "treat as logged in",
                        flush=True,
                    )
                    _push_cdp_progress(
                        progress_queue,
                        CDP_TEXT_PROGRESS_PREFIX,
                        "✅ 检测到登录已完成，继续巡检…",
                    )
                    break
                continue
            form_gone_streak = 0
            # 仅当等待前/期间确实处于登录页，或页面已跳转，才判定登录完成；
            # 防止 Midscene 关闭登录弹窗回到原页时被误判为「已登录」而空跑第二轮
            if seen_login_page or cur != start_url:
                login_ok = True
                recover_via = "manual"
                _push_cdp_progress(
                    progress_queue,
                    CDP_TEXT_PROGRESS_PREFIX,
                    "✅ 检测到登录已完成，继续巡检…",
                )
                break
            if time.time() - last_log >= 60:
                last_log = time.time()
                print(
                    "[CDP] explore login-recover: waiting manual login "
                    f"remain={int(deadline - time.time())}s",
                    flush=True,
                )

    if not login_ok:
        # 等待超时/失败：本轮不重跑，转为停等 —— 用户登录后回复「登录好了」再续跑
        result_context["_cdp_explore_auto_ran"] = False
        msg = (
            f"巡检被登录拦截并已暂停（{why or '登录需人工完成'}）：浏览器已停留在登录页，"
            "请你完成登录后回复「登录好了」（或「继续」），我会接着完成巡检。"
        )
        out["login_blocked"] = True
        out["await_manual_login"] = True
        out["error"] = msg
        out["message"] = msg
        # 断点：待续状态落盘（session + 目标 URL），用户登录后一句话即可续跑（TTL 30 分钟）
        try:
            from agents.cdp.login_pending_store import save_login_pending

            _pending = {
                "session_id": sid,
                "login_type": "explore_login",
                "await_type": "explore_login",
                "url": target_url,
            }
            save_login_pending(
                chat_session_id=chat_session_id,
                project_id=project_id,
                pending=_pending,
            )
            result_context["cdp_login_pending"] = _pending
            print("[CDP] explore login-recover: pending saved for resume", flush=True)
        except Exception as _pend_ex:
            print(f"[CDP] explore login pending save skipped: {_pend_ex}", flush=True)
        _push_cdp_progress(progress_queue, CDP_TEXT_PROGRESS_PREFIX, f"⏸ {msg}")
        print("[CDP] explore login-recover: wait timeout, paused", flush=True)
        return out

    # 3) 登录已解决 → 先导出登录态（下次任务自动复用登录，避免重复登录），再重跑一轮巡检并合并结果
    try:
        _save_res = await tool.execute(
            action="storage_save",
            session_id=sid,
            user_id=uid,
            project_id=project_id,
            url=target_url or None,
        )
        print(
            "[CDP] explore login-recover: storage saved domain="
            f"{(_save_res or {}).get('domain')!r} cookies={(_save_res or {}).get('cookies_count')}",
            flush=True,
        )
    except Exception as _save_ex:
        print(f"[CDP] explore login-recover: storage save skipped: {_save_ex}", flush=True)
    resume_query = (user_input or "").strip() + (
        "\n（重要：登录阻塞已解除，浏览器现已登录。"
        "请对本站主要功能跑一轮完整巡检，覆盖上一轮因登录未能访问的功能。）"
    )
    retry_kw: Dict[str, Any] = {
        "action": "explore",
        "phase": "full",
        "session_id": sid,
        "user_query": resume_query,
        "natural_query": resume_query,
        "result_context": result_context,
    }
    if progress_queue is not None:
        retry_kw["progress_queue"] = progress_queue
    if project_id is not None:
        retry_kw["project_id"] = project_id
    if uid is not None and str(uid).strip():
        retry_kw["user_id"] = uid
    if target_url:
        retry_kw["url"] = target_url
    print(f"[CDP] explore login-recover: rerun explore target={target_url!r}", flush=True)
    try:
        out2 = await tool.execute(**retry_kw)
    except Exception as e:
        out2 = {"success": False, "error": str(e), "action": "explore"}
    if not isinstance(out2, dict):
        out2 = {"success": False, "error": "invalid explore result", "action": "explore"}
    return _merge_explore_outputs(out, out2, via=recover_via)


def _get_cdp_tool(engine: Any) -> Any:
    tools = getattr(engine, "tools", None)
    if tools is None:
        return None
    if hasattr(tools, "get"):
        return tools.get("cdp")
    if isinstance(tools, dict):
        return tools.get("cdp")
    return None


# 「登录好了/继续」等续跑话术：仅当存在 explore 登录待续状态时才作为触发词使用
_EXPLORE_LOGIN_RESUME_WORDS = (
    "登录好了",
    "已登录",
    "已经登录",
    "登录完成",
    "登录成功",
    "登好了",
    "登陆好了",
    "已登陆",
    "登录完毕",
)
_EXPLORE_LOGIN_RESUME_SOFT = ("继续", "接着", "continue", "logged in")


def _explore_login_pending(result_context: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """内存中的 explore 登录待续状态（不含磁盘兜底，读取方均有 build 期注入）。"""
    p = result_context.get("cdp_login_pending") if isinstance(result_context, dict) else None
    if isinstance(p, dict) and p.get("await_type") == "explore_login":
        return p
    return {}


def _is_explore_login_resume_text(user_input: str) -> bool:
    """用户是否在表达「我已登录，继续」。"""
    txt = str(user_input or "").strip()
    if not txt:
        return False
    low = txt.lower()
    if any(w in low for w in _EXPLORE_LOGIN_RESUME_WORDS):
        return True
    if len(txt) <= 14 and any(w in low for w in _EXPLORE_LOGIN_RESUME_SOFT):
        return True
    if len(txt) <= 14 and "好了" in low:
        return True
    return False


def resolve_explore_login_resume(
    user_input: Optional[str],
    *,
    result_context: Optional[Dict[str, Any]],
    chat_session_id: Optional[int] = None,
    project_id: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    """巡检撞登录墙暂停后：用户回复「登录好了/继续」等 → 返回续跑用 cdp navigate 参数。

    命中即清除待续状态（session/url 已进参数），避免后续轮重复注入；
    若续跑后再次被登录拦截，暂停逻辑会重新落盘待续状态。
    """
    from agents.cdp.login_flow import resolve_login_pending

    pending = resolve_login_pending(
        result_context=result_context,
        chat_session_id=chat_session_id,
        project_id=project_id,
    )
    if not isinstance(pending, dict) or pending.get("await_type") != "explore_login":
        return None
    sid = str(pending.get("session_id") or "").strip()
    if not sid:
        return None
    if not _is_explore_login_resume_text(str(user_input or "")):
        return None
    if isinstance(result_context, dict):
        result_context.pop("cdp_login_pending", None)
    try:
        from agents.cdp.login_pending_store import clear_login_pending

        clear_login_pending(chat_session_id=chat_session_id, project_id=project_id)
    except Exception as _clr_ex:
        print(f"[CDP] explore resume pending clear skipped: {_clr_ex}", flush=True)
    params: Dict[str, Any] = {"action": "navigate", "session_id": sid}
    _url = str(pending.get("url") or "").strip()
    if _url:
        params["url"] = _url
    else:
        # 无目标 URL（如只说「探测一下」暂停的场景）：聚焦会话后对当前页继续巡检
        params["action"] = "focus"
    print(f"[CDP] explore login-resume: navigate resume url={_url!r}", flush=True)
    return params


def _should_auto_explore(
    *,
    user_input: str,
    result_context: Dict[str, Any],
) -> bool:
    if result_context.get("_cdp_force_auto_explore"):
        return True
    # 巡检撞登录墙暂停后：用户回复「登录好了/继续」→ 命中续跑
    if _explore_login_pending(result_context) and _is_explore_login_resume_text(user_input):
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
    progress_queue: Any = None,
    chat_session_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    session/navigate/login 成功后，若用户意图为测站/探测，自动跑 cdp explore phase=full
    （默认 Midscene 巡检，见 CDP_EXPLORE_ENGINE）。

    progress_queue：可选进度队列，执行期间向上层透出 Midscene 实时步骤
    （``__CDP_STEP__`` 快照 / ``__CDP_TEXT__`` 阶段文本）。
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
        or _explore_login_pending(result_context).get("session_id")
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
        or _explore_login_pending(result_context).get("url")
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
    if progress_queue is not None:
        call_kw["progress_queue"] = progress_queue
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
                # 只有真实登录成功或「页面已登录/无需登录」才继续；await_credentials/verification 一律转等待
                _login_ok = bool(
                    isinstance(login_out, dict)
                    and (login_out.get("login_success") or login_out.get("login_skipped"))
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
                    if login_out.get("await_user_credentials") and not login_out.get(
                        "await_verification_code"
                    ):
                        # 无可用账密：转人工登录，落盘断点，用户回复「登录好了」即可续跑
                        observation["summary"] = (
                            "巡检需要登录后才能继续：请在浏览器完成登录后"
                            "回复「登录好了」（或「继续」），我会接着完成巡检。"
                        )
                        try:
                            from agents.cdp.login_pending_store import save_login_pending

                            _pending = {
                                "session_id": sid,
                                "login_type": "explore_login",
                                "await_type": "explore_login",
                                "url": url,
                            }
                            save_login_pending(
                                chat_session_id=chat_session_id,
                                project_id=project_id,
                                pending=_pending,
                            )
                            result_context["cdp_login_pending"] = _pending
                            print("[CDP] auto explore: manual-login pending saved", flush=True)
                        except Exception as _pend_ex2:
                            print(
                                f"[CDP] explore login pending save skipped: {_pend_ex2}",
                                flush=True,
                            )
                    else:
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

    # 被登录阻塞 → 自动登录（有配置）或等待人工登录，然后重跑一轮巡检（合并结果）
    try:
        _recovered = await _recover_from_login_block(
            tool,
            out,
            sid=sid,
            uid=uid,
            project_id=project_id,
            target_url=url or "",
            user_input=user_input,
            result_context=result_context,
            progress_queue=progress_queue,
            chat_session_id=chat_session_id,
        )
        if _recovered is not None:
            out = _recovered
    except Exception as _login_rec_ex:
        print(f"[CDP] explore login-recover skipped: {_login_rec_ex}", flush=True)

    # 巡检完成且未被登录阻塞 → 导出登录态，后续任务自动复用（避免重复登录）
    if out.get("success") is not False and not out.get("await_manual_login"):
        try:
            _save_out = await tool.execute(
                action="storage_save",
                session_id=sid,
                user_id=uid,
                project_id=project_id,
                url=url or None,
            )
            print(
                "[CDP] auto explore: storage saved domain="
                f"{(_save_out or {}).get('domain')!r} cookies={(_save_out or {}).get('cookies_count')}",
                flush=True,
            )
        except Exception as _save_ex2:
            print(f"[CDP] auto explore: storage save skipped: {_save_ex2}", flush=True)

    report = _build_explore_report(out, url=url or "")
    if login_note and login_note not in report:
        report = f"{login_note}\n{report}"
    # 巡检完成（含登录恢复后重跑成功）：清掉 explore 登录待续状态，避免后续消息误触发续跑
    if not out.get("await_manual_login"):
        _pend_done = _explore_login_pending(result_context)
        if _pend_done:
            result_context.pop("cdp_login_pending", None)
            try:
                from agents.cdp.login_pending_store import clear_login_pending

                clear_login_pending(chat_session_id=chat_session_id, project_id=project_id)
            except Exception as _clr_ex:
                print(f"[CDP] explore login pending clear skipped: {_clr_ex}", flush=True)
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
        "await_manual_login",
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
