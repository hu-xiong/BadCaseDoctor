# -*- coding: utf-8 -*-
"""本地代理等可执行文件下载（Windows .exe / Unix 无扩展名二进制）；构建后放入 client_binaries/。"""
from __future__ import annotations

import os
import re
import shutil

from flask import Blueprint, Response, jsonify, request, send_from_directory
from flask_login import current_user, login_required

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


def _is_loopback_url(url: str) -> bool:
    rest = (url or "").split("://", 1)[-1]
    host = rest.split("/", 1)[0].rsplit("@", 1)[-1]
    if host.startswith("["):
        host = host[1:].split("]", 1)[0]
    else:
        host = host.split(":", 1)[0]
    host = host.strip().lower()
    return host in ("127.0.0.1", "localhost", "::1") or host.startswith("127.")


def _push_user_tunnel_params() -> Optional[dict]:
    """本机开发（隧道入口在环回）时，把当前登录用户的隧道参数交给运行中的代理。

    云端部署（隧道 URL 是域名）返回 None：注入由用户机器上的前端命令完成（见
    electron-vue3 localProxyStartAndResume.js），避免在服务器上误起代理。
    """
    url = _tunnel_public_url()
    if not _is_loopback_url(url):
        return None
    try:
        if not current_user.is_authenticated:
            return None
        uid = int(current_user.id)
    except Exception:
        return None
    from app_services.tunnel_token import issue_tunnel_token
    from local_proxy_supervisor import push_tunnel_config

    try:
        row = issue_tunnel_token(uid)
    except RuntimeError:
        return None
    st = push_tunnel_config(url, row["token"])
    return {k: st.get(k) for k in ("pushed", "owned", "pid", "last_error")}


@client_scripts_bp.route("/local-proxy/supervisor/ensure", methods=["POST", "GET"])
def local_proxy_supervisor_ensure():
    """按需拉起本机 go-local-proxy（Flask 同机托管）；本机开发下顺带刷新隧道参数。"""
    try:
        from local_proxy_supervisor import ensure_local_proxy_running, probe_local_proxy_ok

        st = dict(ensure_local_proxy_running() or {})
        ok = bool(probe_local_proxy_ok())
        if ok:
            pushed = _push_user_tunnel_params()
            if pushed:
                st["tunnel"] = pushed
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
    return jsonify({"ok": ok, **st}), (200 if ok else 503)


def _tunnel_public_url() -> str:
    """本机代理反连入口：优先 env 覆盖，其次本机开发直连桥端口，最后按请求推导同域地址。"""
    explicit = (os.getenv("BADCASE_TUNNEL_URL") or "").strip()
    if explicit:
        return explicit
    try:
        host = (request.host or "").strip()
    except Exception:
        host = ""
    if not host:
        return ""
    hostname = host.rsplit(":", 1)[0].strip("[]").lower()
    # 本机开发：Flask 与桥服务同机、无 nginx，_tunnel_public_url 推不出桥端口 → 直连环回隧道口
    if hostname in ("127.0.0.1", "localhost", "::1") or hostname.startswith("127."):
        port = (os.getenv("BADCASE_BRIDGE_TUNNEL_PORT") or "9889").strip() or "9889"
        return f"ws://127.0.0.1:{port}/api/local-proxy/tunnel"
    proto = (
        (request.headers.get("X-Forwarded-Proto") or request.scheme or "https")
        .split(",")[0]
        .strip()
        .lower()
    )
    scheme = "wss" if proto == "https" else "ws"
    return f"{scheme}://{host}/api/local-proxy/tunnel"


@client_scripts_bp.route("/local-proxy/tunnel-token", methods=["GET"])
@login_required
def local_proxy_tunnel_token():
    """登录用户获取隧道接入参数（供前端注入 --tunnel-url/--tunnel-token）。

    见 docs/技术设计_本机浏览器CDP通道.md §6.2；密钥未配置时 503 并由前端跳过注入。
    """
    from app_services.tunnel_token import issue_tunnel_token

    try:
        row = issue_tunnel_token(int(current_user.id))
    except RuntimeError as e:
        return jsonify({"ok": False, "error": "tunnel_disabled", "message": str(e)}), 503
    url = _tunnel_public_url()
    if not url:
        return jsonify({"ok": False, "error": "tunnel_url_unresolved"}), 500
    return jsonify(
        {
            "ok": True,
            "url": url,
            "token": row["token"],
            "expires_at": row["expires_at"],
        }
    )


@client_scripts_bp.route("/local-proxy/tunnel-status", methods=["GET"])
@login_required
def local_proxy_tunnel_status():
    """当前登录用户的本机代理隧道是否在线（供前端决定 resume / 注入隧道参数）。

    本机开发下顺手按需拉起桥服务（环回 + 有密钥时；见 local_bridge_supervisor）。
    """
    bridge = None
    try:
        from local_bridge_supervisor import ensure_bridge_running

        bridge = ensure_bridge_running()
    except Exception as e:
        bridge = {"error": str(e)}
    online = False
    device = {}
    try:
        from agents.cdp.channel import tunnel_status

        st = tunnel_status(int(current_user.id))
        online = bool(st.online)
        device = st.device or {}
    except Exception:
        online = False
    return jsonify(
        {
            "ok": True,
            "online": online,
            "device": device,
            "user_id": int(current_user.id),
            "tunnel_url": _tunnel_public_url(),
            "bridge": {
                "health_ok": bool((bridge or {}).get("health_ok")),
                "pid": (bridge or {}).get("pid"),
                "gateway_port": (bridge or {}).get("gateway_port"),
                "skipped": (bridge or {}).get("skipped"),
                "error": (bridge or {}).get("error"),
            },
        }
    )


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
