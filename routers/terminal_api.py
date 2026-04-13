# -*- coding: utf-8 -*-
"""嵌入式终端：AI 命令建议、审计查询（REST；交互式 PTY 由本机 go-local-proxy / Electron 承担）"""
from __future__ import annotations

import csv
import io
import json
import re
from datetime import datetime, timezone

from flask import Blueprint, Response, jsonify, request
from flask_login import current_user, login_required

from config import Config

terminal_bp = Blueprint("terminal", __name__, url_prefix="/api/terminal")

# 高危模式：AI 返回需前端二次确认
_DANGEROUS = re.compile(
    r"(rm\s+-rf|mkfs\.|dd\s+if=|curl\s+[^\n]*\|\s*sh|chmod\s+-R\s+777|shutdown|reboot|>\s*/dev/sd)",
    re.IGNORECASE,
)

_DEFAULT_AI_WHITELIST = (
    "tail,head,cat,less,more,grep,egrep,fgrep,ls,cd,pwd,echo,printf,ps,top,df,du,ss,"
    "netstat,ip,curl,wget,journalctl,systemctl,docker,kubectl,find,sort,uniq,wc,stat,file,"
    "date,whoami,id,groups,env,which,type,where,hostname,uname,dmesg,lsof,strace"
)


def _ai_whitelist_tokens() -> list[str]:
    raw = getattr(Config, "TERMINAL_AI_WHITELIST", None) or ""
    raw = str(raw).strip()
    if raw:
        return [x.strip().lower() for x in raw.split(",") if x.strip()]
    return [x.strip().lower() for x in _DEFAULT_AI_WHITELIST.split(",") if x.strip()]


def _ai_whitelist_enabled() -> bool:
    return bool(getattr(Config, "TERMINAL_AI_WHITELIST_ENABLED", False))


def _first_executable_token(cmd: str) -> str:
    s = (cmd or "").strip()
    if not s:
        return ""
    parts = re.split(r"\s+", s)
    i = 0
    while i < len(parts):
        low = parts[i].lower().strip("\"'")
        if low in ("sudo", "nohup", "nice", "command", "stdbuf"):
            i += 1
            continue
        if low == "-n" and i + 1 < len(parts) and parts[i - 1].lower() == "nice":
            i += 1
            continue
        break
    if i >= len(parts):
        return ""
    tok = parts[i].lower().strip("\"'")
    if tok.startswith("./"):
        tok = tok[2:]
    for sep in ("/", "\\"):
        if sep in tok:
            tok = tok.split(sep)[-1]
    return tok


def _command_allowed_by_whitelist(command: str, allowed: list[str]) -> bool:
    if not allowed:
        return True
    tok = _first_executable_token(command)
    if not tok:
        return False
    return tok in set(allowed)


def _audit_terminal_event(
    *,
    user_id: int,
    event_type: str,
    detail: str | None = None,
    project_id: int | None = None,
    client_session_id: str | None = None,
) -> None:
    try:
        from app import db, TerminalAudit

        row = TerminalAudit(
            user_id=user_id,
            project_id=project_id,
            event_type=event_type[:40],
            client_session_id=(client_session_id or "")[:64] or None,
            detail=(detail or "")[:65000] if detail else None,
        )
        db.session.add(row)
        db.session.commit()
    except Exception:
        try:
            from app import db as _db

            _db.session.rollback()
        except Exception:
            pass


@terminal_bp.route("/ai_suggest", methods=["POST"])
@login_required
def ai_suggest():
    """自然语言 → shell 命令 + 简短解释（JSON）"""
    data = request.get_json() or {}
    prompt = (data.get("prompt") or "").strip()
    if not prompt:
        return jsonify({"success": False, "error": "prompt 不能为空"}), 400

    cwd = (data.get("cwd") or "").strip() or None
    project_id = data.get("project_id")
    os_hint = (data.get("os") or "").strip() or None

    sys_prompt = (
        "你是运维/测试助手。用户会描述想在终端里做的事。"
        "只输出一行合法 JSON，不要 Markdown，不要代码块。"
        '格式：{"command":"单行可执行 shell 命令","explanation":"一句中文说明"}。\n'
        "命令尽量短；不要解释性文字混进 command；优先 POSIX/Linux；若用户环境为 Windows 可适当使用 cmd/PowerShell。\n"
    )
    if cwd:
        sys_prompt += f"当前工作目录（参考）：{cwd}\n"
    if os_hint:
        sys_prompt += f"操作系统提示：{os_hint}\n"
    user_msg = f"用户需求：{prompt}"

    try:
        from llm.dashscope_compat import get_dashscope_compat_client

        client = get_dashscope_compat_client()
        model = getattr(Config, "DASHSCOPE_MODEL", None) or getattr(Config, "QWEN_API_MODEL", None) or "qwen-plus"
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.2,
            max_tokens=512,
        )
        raw = (resp.choices[0].message.content or "").strip()
    except Exception as e:
        return jsonify({"success": False, "error": f"模型调用失败: {e}"}), 500

    command = ""
    explanation = ""
    try:
        # 去掉可能的 ```json 包裹
        if raw.startswith("```"):
            raw = re.sub(r"^```\w*\n?", "", raw)
            raw = re.sub(r"\n?```$", "", raw)
        obj = json.loads(raw)
        command = str(obj.get("command") or "").strip()
        explanation = str(obj.get("explanation") or "").strip()
    except Exception:
        # 兜底：整段当命令
        command = raw.split("\n")[0][:2000]
        explanation = ""

    wl = _ai_whitelist_tokens()
    if _ai_whitelist_enabled() and command and not _command_allowed_by_whitelist(command, wl):
        _audit_terminal_event(
            user_id=current_user.id,
            event_type="ai_suggest_whitelist_block",
            detail=json.dumps(
                {"prompt": prompt[:500], "command": command[:500], "token": _first_executable_token(command)},
                ensure_ascii=False,
            ),
            project_id=int(project_id) if project_id is not None else None,
        )
        return jsonify(
            {
                "success": False,
                "error": "AI 生成的命令不在允许列表内，请换一种描述或联系管理员调整 TERMINAL_AI_WHITELIST。",
                "whitelist_violation": True,
            }
        ), 400

    needs_confirm = bool(command and _DANGEROUS.search(command))

    detail = json.dumps(
        {"prompt": prompt[:2000], "command": command[:2000], "explanation": explanation[:500]},
        ensure_ascii=False,
    )
    _audit_terminal_event(
        user_id=current_user.id,
        event_type="ai_suggest",
        detail=detail,
        project_id=int(project_id) if project_id is not None else None,
    )

    return jsonify(
        {
            "success": True,
            "command": command,
            "explanation": explanation,
            "needs_confirm": needs_confirm,
        }
    )


@terminal_bp.route("/config", methods=["GET"])
def terminal_config():
    """前端展示用：AI 白名单是否开启（不返回完整密钥类信息）。

    故意不加 @login_required：数据仅来自 Config / 环境变量，不查库；若加上登录，
    Flask-Login 的 load_user 会连 MySQL，库不可达时本地嵌入式终端页连「白名单 pill」都拉不到。
    """
    en = _ai_whitelist_enabled()
    tokens = _ai_whitelist_tokens() if en else []
    return jsonify(
        {
            "success": True,
            "ai_whitelist_enabled": en,
            "ai_whitelist_count": len(tokens),
            "ai_whitelist_tokens": tokens[:80],
        }
    )


@terminal_bp.route("/output_diagnose", methods=["POST"])
@login_required
def output_diagnose():
    """终端选中输出 → 中文简要原因与排查建议（不落库命令全文）"""
    data = request.get_json() or {}
    snippet = (data.get("output") or "").strip()
    if not snippet:
        return jsonify({"success": False, "error": "output 不能为空"}), 400
    if len(snippet) > 12000:
        snippet = snippet[:12000]

    cwd = (data.get("cwd") or "").strip() or None
    project_id = data.get("project_id")
    os_hint = (data.get("os") or "").strip() or None

    sys_prompt = (
        "你是运维/测试助手。用户从终端复制了一段命令输出，可能含报错栈或系统消息。"
        "请用中文简洁回答，使用 Markdown 小标题：## 可能原因 ## 建议排查。"
        "不要编造输出中不存在的信息；信息不足时说明需要补充哪些信息。"
    )
    if cwd:
        sys_prompt += f"\n当前工作目录（参考）：{cwd}\n"
    if os_hint:
        sys_prompt += f"操作系统提示：{os_hint}\n"
    user_msg = f"终端输出摘录：\n```\n{snippet}\n```"

    try:
        from llm.dashscope_compat import get_dashscope_compat_client

        client = get_dashscope_compat_client()
        model = getattr(Config, "DASHSCOPE_MODEL", None) or getattr(Config, "QWEN_API_MODEL", None) or "qwen-plus"
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.2,
            max_tokens=1024,
        )
        diagnosis = (resp.choices[0].message.content or "").strip()
    except Exception as e:
        return jsonify({"success": False, "error": f"模型调用失败: {e}"}), 500

    detail = json.dumps(
        {"output_len": len(snippet), "diagnosis_len": len(diagnosis)},
        ensure_ascii=False,
    )
    _audit_terminal_event(
        user_id=current_user.id,
        event_type="output_diagnose",
        detail=detail,
        project_id=int(project_id) if project_id is not None else None,
    )

    return jsonify({"success": True, "diagnosis": diagnosis})


@terminal_bp.route("/audit", methods=["GET"])
@login_required
def audit_list():
    """最近终端审计（简化分页）"""
    try:
        from app import db, TerminalAudit

        page = int(request.args.get("page", 1))
        per_page = min(int(request.args.get("per_page", 30)), 100)
        q = (
            db.session.query(TerminalAudit)
            .filter(TerminalAudit.user_id == current_user.id)
            .order_by(TerminalAudit.created_at.desc())
        )
        total = q.count()
        rows = q.offset((page - 1) * per_page).limit(per_page).all()
        items = []
        for r in rows:
            items.append(
                {
                    "id": r.id,
                    "event_type": r.event_type,
                    "client_session_id": r.client_session_id,
                    "detail": r.detail[:500] if r.detail else None,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
            )
        return jsonify({"success": True, "total": total, "items": items})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@terminal_bp.route("/audit/export", methods=["GET"])
@login_required
def audit_export_csv():
    """当前用户终端审计记录导出为 CSV（UTF-8 BOM，便于 Excel 打开）"""
    try:
        from app import db, TerminalAudit

        limit = min(int(request.args.get("limit", 5000)), 20000)
        rows = (
            db.session.query(TerminalAudit)
            .filter(TerminalAudit.user_id == current_user.id)
            .order_by(TerminalAudit.created_at.desc())
            .limit(limit)
            .all()
        )
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["id", "project_id", "event_type", "client_session_id", "created_at", "detail"])
        for r in rows:
            detail = (r.detail or "").replace("\r\n", " ").replace("\n", " ")[:65000]
            w.writerow(
                [
                    r.id,
                    r.project_id if r.project_id is not None else "",
                    r.event_type or "",
                    r.client_session_id or "",
                    r.created_at.isoformat() if r.created_at else "",
                    detail,
                ]
            )
        text = "\ufeff" + buf.getvalue()
        return Response(
            text.encode("utf-8"),
            mimetype="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": 'attachment; filename="terminal_audit.csv"',
                "Cache-Control": "no-store",
            },
        )
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
