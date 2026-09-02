# -*- coding: utf-8 -*-
"""Midscene 执行桥：Python 调用 agents/midscene_runner/smoke.mjs。"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_RUNNER_DIR = Path(__file__).resolve().parents[1] / "midscene_runner"
_SMOKE_JS = _RUNNER_DIR / "smoke.mjs"


def explore_engine() -> str:
    """midscene | legacy | auto（默认 midscene，失败可按 auto 回退）。"""
    return (os.getenv("CDP_EXPLORE_ENGINE", "midscene") or "midscene").strip().lower()


def midscene_model_configured() -> bool:
    key = (os.getenv("MIDSCENE_MODEL_API_KEY") or "").strip()
    name = (os.getenv("MIDSCENE_MODEL_NAME") or "").strip()
    return bool(key and name)


def midscene_runner_ready() -> bool:
    if not _SMOKE_JS.is_file():
        return False
    node_modules = _RUNNER_DIR / "node_modules" / "@midscene" / "web"
    return node_modules.is_dir()


def default_smoke_goal(user_query: str = "") -> str:
    q = (user_query or "").strip()
    base = (
        "你是一名认真的手工测试同学。请像正常人一样先把这个 Web 系统的主要界面功能走一遍："
        "确认页面可打开；浏览导航/侧栏/Tab；空状态则尝试新建并保存主业务对象；"
        "尝试搜索/筛选/打开详情；不要点删除/注销/退出；日期与下拉用正常点选。"
        "最后停留在可观察结果的页面。"
    )
    if q:
        return f"{base}\n用户补充意图：{q[:500]}"
    return base


def map_midscene_result_to_explore_observation(raw: Dict[str, Any], *, url: str = "") -> Dict[str, Any]:
    """把 runner JSON 映射为与 legacy explore 兼容的 observation 字段。"""
    if not isinstance(raw, dict):
        return {
            "success": False,
            "engine": "midscene",
            "error": "invalid midscene result",
            "fallback_legacy": True,
        }

    if raw.get("fallback_legacy"):
        return {
            "success": False,
            "engine": "midscene",
            "error": raw.get("error") or "midscene unavailable",
            "fallback_legacy": True,
            "message": raw.get("error"),
        }

    failed = raw.get("failed") if isinstance(raw.get("failed"), list) else []
    passed = raw.get("passed") if isinstance(raw.get("passed"), list) else []
    tested = raw.get("tested_flows") if isinstance(raw.get("tested_flows"), list) else []
    blocking = bool(raw.get("has_blocking_bug"))
    issues: List[Dict[str, Any]] = []
    for item in failed:
        if isinstance(item, dict):
            step = str(item.get("step") or "操作失败")
            reason = str(item.get("reason") or "")
            msg = f"{step}：{reason}".strip("：")
        else:
            msg = str(item)
        issues.append(
            {
                "type": "midscene_failed",
                "message": msg[:500],
                "severity": "high" if blocking else "medium",
            }
        )

    success = bool(raw.get("success")) and not blocking and not issues
    summary = str(raw.get("summary") or "").strip()
    if not summary:
        parts = [
            "Midscene 界面巡检已完成。",
            f"页面：{raw.get('url') or url or ''}",
            f"已测入口 {len(tested)} 个，通过 {len(passed)}，失败 {len(failed)}。",
        ]
        if tested:
            parts.append("已测：" + "；".join(str(x) for x in tested[:8]))
        if passed:
            parts.append("通过：" + "；".join(str(x) for x in passed[:8]))
        if failed:
            parts.append("失败：" + "；".join(
                (f"{i.get('step')}:{i.get('reason')}" if isinstance(i, dict) else str(i))
                for i in failed[:5]
            ))
        summary = "\n".join(parts)

    out: Dict[str, Any] = {
        "success": success,
        "engine": "midscene",
        "action": "explore",
        "phase": "midscene_smoke",
        "summary": summary[:2000],
        "tested_flows": tested,
        "passed": passed,
        "failed": failed,
        "has_blocking_bug": blocking,
        "has_obvious_issues": blocking or any(
            str(i.get("severity")) == "high" for i in issues
        ),
        "exploration_issues": issues,
        "issues_found": len(issues),
        "element_count": len(tested) or len(passed),
        "exploration_clicks": None,
        "exploration_fills": None,
        "midscene_report_file": raw.get("report_file") or "",
        "empty_state_seen": bool(raw.get("empty_state_seen")),
        "duration_ms": raw.get("duration_ms"),
        "page": {
            "url": raw.get("url") or url,
            "title": raw.get("page_title") or "",
        },
        "error": raw.get("error"),
        "message": raw.get("error") or summary[:500],
    }
    if issues and (blocking or out["has_obvious_issues"]):
        actual = "\n".join(str(i.get("message") or "") for i in issues)[:2000]
        out["cdp_test_evidence"] = {
            "test_failed": True,
            "failed_at_action": "midscene_explore",
            "issues": issues,
            "steps_to_reproduce": summary[:3000],
            "actual_result": actual,
            "expected_result": "主界面功能可正常使用，无阻塞性错误",
            "suggested_create_target": "bug",
            "suggested_create_fields": {
                "title": (issues[0].get("message") or "Midscene 巡检失败")[:120],
                "description": summary[:2000],
                "steps_to_reproduce": summary[:3000],
                "actual_result": actual,
                "expected_result": "主界面功能可正常使用，无阻塞性错误",
            },
        }
    return out


def _resolve_node_bin() -> Optional[str]:
    return shutil.which("node") or shutil.which("node.exe")


async def run_midscene_smoke(
    *,
    url: str,
    goal: Optional[str] = None,
    headless: Optional[bool] = None,
    timeout_sec: Optional[int] = None,
    cdp_ws_url: Optional[str] = None,
) -> Dict[str, Any]:
    """子进程执行 Midscene smoke，返回原始 JSON。"""
    if not midscene_runner_ready():
        return {
            "success": False,
            "engine": "midscene",
            "error": (
                "Midscene runner 未就绪：请在 agents/midscene_runner 执行 "
                "npm install && npx playwright install chromium"
            ),
            "fallback_legacy": True,
        }
    if not midscene_model_configured():
        return {
            "success": False,
            "engine": "midscene",
            "error": (
                "未配置 Midscene 模型：请设置 MIDSCENE_MODEL_API_KEY / "
                "MIDSCENE_MODEL_NAME / MIDSCENE_MODEL_BASE_URL / MIDSCENE_MODEL_FAMILY"
            ),
            "fallback_legacy": True,
        }
    node = _resolve_node_bin()
    if not node:
        return {
            "success": False,
            "engine": "midscene",
            "error": "未找到 node 可执行文件",
            "fallback_legacy": True,
        }

    if headless is None:
        headless = (os.getenv("CDP_HEADLESS", "1") or "1").strip() not in ("0", "false", "no")
    try:
        timeout_sec = int(timeout_sec or os.getenv("MIDSCENE_SMOKE_TIMEOUT_SEC", "300"))
    except (TypeError, ValueError):
        timeout_sec = 300

    payload = {
        "url": url,
        "goal": goal or default_smoke_goal(),
        "headless": bool(headless),
        "cdp_ws_url": (cdp_ws_url or "").strip() or None,
    }

    with tempfile.TemporaryDirectory(prefix="bcd_midscene_") as td:
        input_path = Path(td) / "input.json"
        input_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        env = os.environ.copy()
        env["MIDSCENE_SMOKE_INPUT"] = str(input_path)
        # Midscene reports under runner cwd
        env.setdefault("PW_TEST_SCREENSHOT_NO_FONTS_READY", "1")

        proc = await asyncio.create_subprocess_exec(
            node,
            str(_SMOKE_JS),
            cwd=str(_RUNNER_DIR),
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_sec)
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except Exception:
                pass
            return {
                "success": False,
                "engine": "midscene",
                "error": f"Midscene 超时（>{timeout_sec}s）",
                "fallback_legacy": False,
            }

        err_text = (stderr or b"").decode("utf-8", errors="replace")
        out_text = (stdout or b"").decode("utf-8", errors="replace").strip()
        if err_text:
            logger.info("[midscene] stderr (tail): %s", err_text[-2000:])

        if not out_text:
            return {
                "success": False,
                "engine": "midscene",
                "error": f"Midscene 无输出，exit={proc.returncode}; stderr={err_text[-800:]}",
                "fallback_legacy": "Cannot find module" in err_text or "ERR_MODULE" in err_text,
            }

        # stdout 应为纯 JSON；若混入日志，取最后一个 {…}
        try:
            raw = json.loads(out_text)
        except json.JSONDecodeError:
            start = out_text.rfind("{")
            end = out_text.rfind("}")
            if start >= 0 and end > start:
                try:
                    raw = json.loads(out_text[start : end + 1])
                except json.JSONDecodeError:
                    return {
                        "success": False,
                        "engine": "midscene",
                        "error": f"无法解析 Midscene JSON: {out_text[:500]}",
                        "fallback_legacy": False,
                    }
            else:
                return {
                    "success": False,
                    "engine": "midscene",
                    "error": f"无法解析 Midscene JSON: {out_text[:500]}",
                    "fallback_legacy": False,
                }
        if isinstance(raw, dict):
            return raw
        return {
            "success": False,
            "engine": "midscene",
            "error": "midscene result not object",
            "fallback_legacy": False,
        }


async def run_midscene_exploration(
    *,
    url: str,
    user_query: str = "",
    headless: Optional[bool] = None,
) -> Dict[str, Any]:
    raw = await run_midscene_smoke(
        url=url,
        goal=default_smoke_goal(user_query),
        headless=headless,
    )
    return map_midscene_result_to_explore_observation(raw, url=url)
