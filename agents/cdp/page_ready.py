# -*- coding: utf-8 -*-
"""登录后 / 探测前：等待项目详情页与侧栏控件渲染完成。"""

from __future__ import annotations

import asyncio
import re
import time
from typing import Any, Optional

_PROJECT_DETAIL_RE = re.compile(r"project-detail/(\d+)", re.I)

# PlansPanel「新建迭代」等侧栏控件
_PROJECT_DETAIL_READY_SELECTORS = (
    'button.action-icon-btn[aria-label="新建迭代"]',
    'button.action-icon-btn:has-text("新建迭代")',
    ".sidebar-content .action-icon-btn",
    ".left-sidebar-host",
    ".project-detail-main",
)


def is_project_detail_url(url: str) -> bool:
    return bool(_PROJECT_DETAIL_RE.search(url or ""))


def project_id_from_url(url: str) -> Optional[int]:
    m = _PROJECT_DETAIL_RE.search(url or "")
    if not m:
        return None
    try:
        return int(m.group(1))
    except (TypeError, ValueError):
        return None


async def wait_for_project_detail_ready(page: Any, *, timeout_ms: int = 12000) -> bool:
    """
    等待 URL 进入 project-detail 且侧栏「新建迭代」等主控件可见。
    登录成功后 Vue 路由 + ensure-default 异步，需短暂等待再 snapshot/点击。
    """
    deadline = time.perf_counter() + timeout_ms / 1000.0
    saw_detail_url = False

    while time.perf_counter() < deadline:
        try:
            url = page.url or ""
        except Exception:
            url = ""

        if is_project_detail_url(url):
            saw_detail_url = True

        if saw_detail_url:
            for sel in _PROJECT_DETAIL_READY_SELECTORS:
                try:
                    loc = page.locator(sel)
                    if await loc.count() > 0 and await loc.first.is_visible(timeout=400):
                        await asyncio.sleep(0.35)
                        return True
                except Exception:
                    continue

        await asyncio.sleep(0.25)

    return saw_detail_url


async def wait_for_post_login_landing(page: Any, *, timeout_ms: int = 15000) -> dict:
    """
    登录提交后：先离开 login URL，再等待进入项目详情（产品默认落点）。
  若短暂停在 project-manage，继续等待前端自动跳转到 project-detail。
    """
    from .login_flow import is_login_url

    deadline = time.perf_counter() + timeout_ms / 1000.0
    left_login = False
    last_url = ""

    while time.perf_counter() < deadline:
        try:
            last_url = page.url or ""
        except Exception:
            last_url = ""

        if not is_login_url(last_url):
            left_login = True
            break
        await asyncio.sleep(0.25)

    if not left_login:
        return {
            "ready": False,
            "url": last_url,
            "on_project_detail": False,
            "message": "登录后仍停留在登录页",
        }

    detail_ready = await wait_for_project_detail_ready(page, timeout_ms=max(5000, timeout_ms))
    try:
        last_url = page.url or ""
    except Exception:
        pass

    on_detail = is_project_detail_url(last_url)
    return {
        "ready": detail_ready or on_detail,
        "url": last_url,
        "on_project_detail": on_detail,
        "project_id": project_id_from_url(last_url),
        "message": "已进入项目详情" if on_detail else "已离开登录页但未进入项目详情",
    }
