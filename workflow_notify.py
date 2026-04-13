# -*- coding: utf-8 -*-
"""
工作项（BadCase / Bug / TestCase）创建、修改、状态流转后的通知：
- 邮件：复用 Flask-Mail 的 send_email
- 飞书 / 钉钉：通过本机 CLI 进程接收 JSON（stdin），由你在 CLI 内调用官方工具

环境变量（均在 .env 中配置即可）：
- WORKFLOW_NOTIFY_FEISHU_CLI      飞书通知 CLI 可执行文件路径（留空则跳过）
- WORKFLOW_NOTIFY_DINGTALK_CLI    钉钉通知 CLI 可执行文件路径（留空则跳过）
- WORKFLOW_NOTIFY_EMAIL_ENABLED   是否发送邮件，默认 true

CLI 约定：启动后从 stdin 读取一行或多行 UTF-8 JSON（单行即可），字段示例：
{
  "channel": "feishu",
  "event": "created|updated|status_changed|deleted|closed",
  "entity_type": "badcase|bug|testcase",
  "entity_id": 1,
  "title": "...",
  "status": "new",
  "previous_status": null,
  "project_id": 1,
  "project_name": "...",
  "actor_id": 2,
  "actor_name": "...",
  "recipients": [{"user_id": 3, "email": "a@b.com", "name": "hx"}]
}
飞书 CLI 收到 channel=feishu，钉钉收到 channel=dingtalk（两次调用各传一份 payload）。
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import threading
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


def _truthy(val: Optional[str], default: bool = True) -> bool:
    if val is None:
        return default
    return str(val).strip().lower() in ("1", "true", "yes", "on")


def _resolve_executable(path: str) -> Optional[str]:
    p = (path or "").strip().strip('"')
    if not p:
        return None
    if os.path.isfile(p):
        return p
    return shutil.which(p)


def _run_cli(channel: str, exe: str, payload: Dict[str, Any]) -> None:
    resolved = _resolve_executable(exe)
    if not resolved:
        logger.warning("[workflow_notify] CLI 未找到或不可执行: %s (%s)", channel, exe)
        return
    body = {**payload, "channel": channel}
    raw = json.dumps(body, ensure_ascii=False, default=str)
    try:
        proc = subprocess.run(
            [resolved],
            input=raw.encode("utf-8"),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=int(os.environ.get("WORKFLOW_NOTIFY_CLI_TIMEOUT", "60")),
            check=False,
        )
        if proc.returncode != 0:
            logger.warning(
                "[workflow_notify] %s CLI exit=%s stderr=%s",
                channel,
                proc.returncode,
                (proc.stderr or b"").decode("utf-8", errors="replace")[:2000],
            )
    except subprocess.TimeoutExpired:
        logger.warning("[workflow_notify] %s CLI 超时: %s", channel, resolved)
    except Exception as e:
        logger.exception("[workflow_notify] %s CLI 异常: %s", channel, e)


def dispatch_workflow_notification(
    payload: Dict[str, Any],
    send_email_fn: Optional[Callable[[str, str, str], bool]] = None,
) -> None:
    """同步发送：CLI + 邮件。出错只记日志，不向外抛。"""
    feishu_cli = os.environ.get("WORKFLOW_NOTIFY_FEISHU_CLI", "").strip()
    ding_cli = os.environ.get("WORKFLOW_NOTIFY_DINGTALK_CLI", "").strip()
    email_on = _truthy(os.environ.get("WORKFLOW_NOTIFY_EMAIL_ENABLED"), True)

    if feishu_cli:
        _run_cli("feishu", feishu_cli, payload)
    if ding_cli:
        _run_cli("dingtalk", ding_cli, payload)

    if not email_on or not send_email_fn:
        return

    recipients: List[Dict[str, Any]] = payload.get("recipients") or []
    if not recipients:
        return

    subject = payload.get("email_subject") or "[BadCase Doctor] 工作项通知"
    body = payload.get("email_body") or ""
    seen = set()
    for r in recipients:
        email = (r.get("email") or "").strip()
        if not email or "@" not in email:
            continue
        key = email.lower()
        if key in seen:
            continue
        seen.add(key)
        try:
            send_email_fn(email, subject, body)
        except Exception as e:
            logger.exception("[workflow_notify] 邮件发送失败 %s: %s", email, e)


def schedule_workflow_notification(
    payload: Dict[str, Any],
    send_email_fn: Optional[Callable[[str, str, str], bool]] = None,
) -> None:
    """异步调度，避免阻塞 HTTP 请求。"""

    def _job() -> None:
        try:
            dispatch_workflow_notification(payload, send_email_fn=send_email_fn)
        except Exception as e:
            logger.exception("[workflow_notify] 异步任务失败: %s", e)

    threading.Thread(target=_job, daemon=True).start()


def build_email_body_cn(payload: Dict[str, Any]) -> str:
    lines = [
        f"事件: {payload.get('event')}",
        f"类型: {payload.get('entity_type')}",
        f"编号: {payload.get('entity_id')}",
        f"标题: {payload.get('title')}",
        f"项目: {payload.get('project_name')} (id={payload.get('project_id')})",
        f"当前状态: {payload.get('status')}",
    ]
    ps = payload.get("previous_status")
    if ps is not None and str(ps) != "":
        lines.append(f"前一状态: {ps}")
    lines.append(f"操作人: {payload.get('actor_name')} (id={payload.get('actor_id')})")
    lines.append("")
    lines.append("此邮件由 BadCase Doctor 自动发送；飞书/钉钉如需单独配置，请使用 CLI 接收 JSON。")
    return "\n".join(lines)


def build_email_subject_cn(payload: Dict[str, Any]) -> str:
    et = payload.get("entity_type") or ""
    ev = payload.get("event") or ""
    tid = payload.get("entity_id")
    title = (payload.get("title") or "")[:60]
    return f"[BadCase Doctor][{et}][{ev}] #{tid} {title}".strip()
