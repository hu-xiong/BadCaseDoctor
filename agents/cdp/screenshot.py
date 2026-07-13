# -*- coding: utf-8 -*-
"""CDP 页面截图：Playwright 捕获 → MinIO → 同源代理 URL。"""

from __future__ import annotations

import html
import os
import re
import time
from io import BytesIO
from typing import Any, Optional


def cdp_screenshot_enabled() -> bool:
    return (os.getenv("CDP_SCREENSHOT_ENABLED", "1") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def _safe_tag(tag: str) -> str:
    s = re.sub(r"[^\w\-]+", "_", str(tag or "step").strip())[:48]
    return s or "step"


def upload_png_bytes(png: bytes, *, folder: str, filename: str) -> Optional[str]:
    """上传 PNG 到 MinIO，返回 /api/uploads/image/... 代理 URL。"""
    if not png:
        return None
    try:
        buf = BytesIO(png)
        buf.filename = filename  # type: ignore[attr-defined]
        try:
            from app_services.minio_storage import upload_file_to_minio
        except ImportError:
            from app import upload_file_to_minio  # type: ignore

        result = upload_file_to_minio(buf, folder_path=folder)
        if isinstance(result, dict) and result.get("success"):
            return str(result.get("url") or "").strip() or None
    except Exception:
        pass
    return None


async def capture_page_png(page: Any) -> bytes:
    return await page.screenshot(type="png", full_page=False)


async def capture_and_upload_cdp_screenshot(
    page: Any,
    *,
    session_id: str,
    tag: str,
) -> Optional[str]:
    if not cdp_screenshot_enabled():
        return None
    try:
        png = await capture_page_png(page)
        sid = _safe_tag(session_id or "sess")[:16]
        fname = f"cdp_{sid}_{_safe_tag(tag)}_{int(time.time())}.png"
        return upload_png_bytes(png, folder="cdp", filename=fname)
    except Exception:
        return None


def format_steps_html_with_screenshot(
    text: str,
    screenshot_url: Optional[str],
    *,
    alt: str = "CDP 失败截图",
) -> str:
    """复现步骤 HTML：文字 + 截图 img（RichTextHtmlEditor 可渲染）。"""
    body = str(text or "").strip()
    url = str(screenshot_url or "").strip()
    if not url:
        return body[:8000]
    if body.startswith("<"):
        text_part = body
    elif body:
        text_part = f"<p>{html.escape(body)}</p>"
    else:
        text_part = ""
    img = f'<p><img src="{html.escape(url, quote=True)}" alt="{html.escape(alt)}" class="rte-inline-img"></p>'
    combined = f"{text_part}\n{img}".strip() if text_part else img
    return combined[:8000]
