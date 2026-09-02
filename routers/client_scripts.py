# -*- coding: utf-8 -*-
"""本地代理等可执行文件下载（Windows .exe / Unix 无扩展名二进制）；构建后放入 client_binaries/。"""
from __future__ import annotations

import os
import re
import shutil

from flask import Blueprint, Response, jsonify, request, send_from_directory
from flask_login import login_required

from badcase_client_binaries import LOCAL_PROXY_ARTIFACTS, client_binaries_dir, local_proxy_artifacts_for_api

client_scripts_bp = Blueprint("client_scripts", __name__, url_prefix="/api/client-scripts")

_ALLOWED_NAMES = {a["filename"] for a in LOCAL_PROXY_ARTIFACTS}


def _allow_loopback_local_save() -> bool:
    """仅本机环回调用，避免登录用户把路径写到远端服务器磁盘上。"""
    raw = (os.getenv("BADCASE_RELAX_LOCAL_PROXY_SAVE_HOST") or "").strip().lower()
    if raw in ("1", "true", "yes", "on"):
        return True
    addr = (request.remote_addr or "").strip()
    if addr in ("127.0.0.1", "::1", "localhost"):
        return True
    return False


def _normalize_target_path(raw: str) -> str:
    s = (raw or "").strip()
    if not s or "\x00" in s:
        raise ValueError("invalid_path")
    # 规范化 .. 等
    if os.name == "nt":
        if not re.match(r"^([a-zA-Z]:[\\/]|\\\\)", s):
            raise ValueError("need_absolute_path")
    else:
        if not s.startswith("/"):
            raise ValueError("need_absolute_path")
    return os.path.normpath(s)


def _basename_allowed(name: str) -> bool:
    base = os.path.basename(name.replace("\\", "/"))
    return base in _ALLOWED_NAMES


@client_scripts_bp.route("/local-proxy/manifest.json", methods=["GET"])
def local_proxy_manifest():
    return jsonify(
        {
            "version": 1,
            "name": "badcase-local-proxy",
            "artifacts": local_proxy_artifacts_for_api(),
        }
    )


@client_scripts_bp.route("/local-proxy/supervisor", methods=["GET"])
def local_proxy_supervisor_status():
    """本机 Flask 是否托管 go-local-proxy（启停状态；供前端展示）。"""
    try:
        from local_proxy_supervisor import supervisor_status

        st = supervisor_status()
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
    return jsonify({"ok": True, **st})


@client_scripts_bp.route("/local-proxy/supervisor/ensure", methods=["POST", "GET"])
def local_proxy_supervisor_ensure():
    """按需拉起本机 go-local-proxy（Flask 同机托管）；返回探测结果。"""
    try:
        from local_proxy_supervisor import ensure_local_proxy_running, probe_local_proxy_ok

        st = ensure_local_proxy_running()
        ok = bool(probe_local_proxy_ok())
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
    return jsonify({"ok": ok, **(st or {})}), (200 if ok else 503)


@client_scripts_bp.route("/local-proxy/save", methods=["POST"])
@login_required
def save_local_proxy_to_disk():
    """
    浏览器无法直接写任意磁盘路径时，由「与浏览器同机运行的」后端代为写入。
    仅允许来自环回地址的请求，且需登录。
    """
    if not _allow_loopback_local_save():
        return (
            jsonify(
                {
                    "ok": False,
                    "error": "not_loopback",
                    "message": "该接口仅允许从本机（127.0.0.1）访问后端时使用；远程部署请勿开启。",
                }
            ),
            403,
        )

    target_raw = (request.form.get("target_path") or request.form.get("path") or "").strip()
    try:
        abs_path = _normalize_target_path(target_raw)
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e.args[0] if e.args else "invalid_path"), "message": "路径无效，请填写绝对路径（含盘符或从 / 开始）。"}), 400

    if not _basename_allowed(abs_path):
        return (
            jsonify(
                {
                    "ok": False,
                    "error": "bad_filename",
                    "message": f"文件名必须是已发布的制品之一：{', '.join(sorted(_ALLOWED_NAMES))}",
                }
            ),
            400,
        )

    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify({"ok": False, "error": "missing_file", "message": "缺少文件内容。"}), 400

    parent = os.path.dirname(abs_path)
    try:
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(abs_path, "wb") as out:
            shutil.copyfileobj(f.stream, out, length=1024 * 1024)
    except OSError as e:
        return jsonify({"ok": False, "error": "write_failed", "message": str(e)}), 500

    return jsonify({"ok": True, "path": abs_path})


@client_scripts_bp.route("/bin/<path:name>", methods=["GET"])
def download_bin(name):
    if name not in _ALLOWED_NAMES or name != os.path.basename(name):
        return jsonify({"error": "unknown artifact", "name": name}), 404
    d = client_binaries_dir()
    path = os.path.join(d, name)
    if not os.path.isfile(path):
        return (
            jsonify(
                {
                    "error": "binary_not_deployed",
                    "message": "服务端尚未放置该平台的构建产物，请在 go-local-proxy 目录执行 go build 后将文件复制到 client_binaries/。",
                    "expected_dir": d,
                    "filename": name,
                }
            ),
            404,
        )
    return send_from_directory(d, name, as_attachment=True, download_name=name)


# 兼容旧链接：仍提供占位 shell（无对应 exe 时客户可改用 manifest 下载）
_AGENT_BRIDGE_SH = r"""#!/usr/bin/env bash
set -euo pipefail
echo "请优先使用对话面板提供的「本地代理」Windows/macOS/Linux 可执行文件下载。"
echo "若仅有本脚本：请将浏览器当前站点作为 API 基地址，并按内部文档配置。"
exit 0
"""


@client_scripts_bp.route("/agent-bridge.sh", methods=["GET"])
def download_agent_bridge_sh():
    return Response(
        _AGENT_BRIDGE_SH,
        mimetype="text/x-shellscript; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="badcase-agent-bridge.sh"',
            "Cache-Control": "public, max-age=300",
        },
    )
