# -*- coding: utf-8 -*-
"""
嵌入式终端：Socket.IO + 多会话（client_session_id）+ 本地 PTY + SSH(paramiko)。
需登录；事件负载均带 client_session_id 供前端多 Tab 路由。
"""
from __future__ import annotations

import base64
import errno
import json
import os
import select
import struct
import sys
import threading
import time
import logging

from flask import request, session

log = logging.getLogger(__name__)


def _terminal_uid():
    """Socket.IO 里优先读 session；部分环境下 Flask-Login 的 current_user 更可靠。"""
    try:
        raw = session.get("_user_id")
        if raw is not None:
            return int(raw)
    except Exception:
        pass
    try:
        from flask_login import current_user

        if getattr(current_user, "is_authenticated", False) and current_user.get_id() is not None:
            return int(current_user.get_id())
    except Exception:
        pass
    return None

_socketio = None
_app = None

# socket.io connection id -> { csid: session_info }
_sessions: dict[str, dict[str, dict]] = {}

MAX_SESSIONS = 5

_HAS_UNIX_PTY = sys.platform != "win32"

# pywinpty 3.x 起顶层包名为 winpty；2.x 为 pywinpty。两者不可混用导入。
WinPtyProcess = None  # type: ignore
_HAS_WIN_PTY = False
if sys.platform == "win32":
    try:
        from winpty import PtyProcess as WinPtyProcess  # pywinpty >= 3
        _HAS_WIN_PTY = True
    except Exception:
        try:
            from pywinpty import PtyProcess as WinPtyProcess  # pywinpty 2
            _HAS_WIN_PTY = True
        except Exception:
            WinPtyProcess = None  # type: ignore
            _HAS_WIN_PTY = False

try:
    import paramiko

    _HAS_PARAMIKO = True
except Exception:
    paramiko = None  # type: ignore
    _HAS_PARAMIKO = False


def _b64e(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _emit_out(socket_sid: str, csid: str, raw: bytes) -> None:
    if _socketio is None:
        return
    _socketio.emit(
        "term_output",
        {"b64": _b64e(raw), "client_session_id": csid},
        room=socket_sid,
    )


def _emit_exit(socket_sid: str, csid: str) -> None:
    if _socketio is None:
        return
    try:
        _socketio.emit("term_exit", {"ok": True, "client_session_id": csid}, room=socket_sid)
    except Exception:
        pass


def _audit(app, user_id: int, event_type: str, detail: str | None, csid: str | None, project_id: int | None = None):
    try:
        with app.app_context():
            from app import db, TerminalAudit

            row = TerminalAudit(
                user_id=user_id,
                project_id=project_id,
                event_type=event_type[:40],
                client_session_id=(csid or "")[:64] or None,
                detail=(detail or "")[:65000] if detail else None,
            )
            db.session.add(row)
            db.session.commit()
    except Exception as e:
        log.debug("terminal audit: %s", e)
        try:
            with app.app_context():
                from app import db as _db

                _db.session.rollback()
        except Exception:
            pass


def _cleanup_one(socket_sid: str, csid: str) -> None:
    bucket = _sessions.get(socket_sid)
    if not bucket:
        return
    info = bucket.pop(csid, None)
    if not info:
        return
    try:
        kind = info.get("kind")
        if kind == "win" and info.get("proc"):
            p = info["proc"]
            try:
                if hasattr(p, "isalive") and p.isalive():
                    p.close()
            except Exception:
                pass
        elif kind == "unix" and info.get("fd") is not None:
            fd = info["fd"]
            try:
                os.close(fd)
            except Exception:
                pass
        elif kind == "ssh":
            ch = info.get("chan")
            ssh = info.get("ssh_client")
            try:
                if ch:
                    ch.close()
            except Exception:
                pass
            try:
                if ssh:
                    ssh.close()
            except Exception:
                pass
    except Exception as e:
        log.debug("cleanup_one: %s", e)


def _cleanup_socket(socket_sid: str) -> None:
    bucket = _sessions.pop(socket_sid, None)
    if not bucket:
        return
    for csid in list(bucket.keys()):
        _cleanup_one(socket_sid, csid)


def _reader_win(socket_sid: str, csid: str, proc) -> None:
    while True:
        try:
            if hasattr(proc, "isalive") and not proc.isalive():
                break
            try:
                chunk = proc.read(65536, blocking=True)
            except TypeError:
                # pywinpty 3 / winpty：read(size)，返回 str
                chunk = proc.read(65536)
            if chunk is None:
                break
            if isinstance(chunk, str):
                out = chunk.encode("utf-8", errors="replace")
            else:
                out = chunk
            if not out:
                # pywinpty>=3 / winpty：PTY 侧无输出时用 '0011Ignore' 占位，read() 会变成空串，绝非 EOF
                continue
            _emit_out(socket_sid, csid, out)
        except EOFError:
            break
        except Exception as e:
            log.debug("win reader: %s", e)
            break
    _emit_exit(socket_sid, csid)


def _reader_unix(socket_sid: str, csid: str, master_fd: int) -> None:
    while True:
        try:
            r, _, _ = select.select([master_fd], [], [], 0.2)
            if master_fd not in r:
                continue
            data = os.read(master_fd, 65536)
            if not data:
                break
            _emit_out(socket_sid, csid, data)
        except OSError as e:
            if e.errno in (errno.EIO, errno.EBADF):
                break
            log.debug("unix reader: %s", e)
            break
        except Exception as e:
            log.debug("unix reader: %s", e)
            break
    _emit_exit(socket_sid, csid)


def _reader_ssh(socket_sid: str, csid: str, chan) -> None:
    while True:
        try:
            if chan.closed:
                break
            if chan.recv_ready():
                data = chan.recv(65536)
                if not data:
                    break
                _emit_out(socket_sid, csid, data)
            elif chan.exit_status_ready():
                break
            else:
                time.sleep(0.04)
        except Exception as e:
            log.debug("ssh reader: %s", e)
            break
    _emit_exit(socket_sid, csid)


def _set_winsize_unix(fd: int, rows: int, cols: int) -> None:
    try:
        import fcntl as _fn
        import termios as _tm

        winsize = struct.pack("HHHH", rows, cols, 0, 0)
        _fn.ioctl(fd, _tm.TIOCSWINSZ, winsize)
    except Exception as e:
        log.debug("setwinsize unix: %s", e)


def _unix_fork_pty(cwd: str | None, rows: int, cols: int) -> int:
    import pty as pty_mod

    pid, master_fd = pty_mod.fork()
    if pid == 0:
        try:
            if cwd and os.path.isdir(cwd):
                os.chdir(cwd)
        except Exception:
            pass
        os.environ.setdefault("TERM", "xterm-256color")
        sh = os.environ.get("SHELL") or "/bin/bash"
        os.execl(sh, sh)
    _set_winsize_unix(master_fd, rows, cols)
    return master_fd


def _start_local_pty(socket_sid: str, csid: str, cols: int, rows: int, cwd: str | None) -> tuple[bool, str]:
    if _HAS_WIN_PTY and WinPtyProcess is not None:
        try:
            log.warning("[term] start_local_pty(win) sid=%s csid=%s rows=%s cols=%s cwd=%s", socket_sid, csid, rows, cols, cwd)
            shell = os.environ.get("COMSPEC") or os.environ.get("SystemRoot", "C:\\Windows") + "\\System32\\cmd.exe"
            if not os.path.isfile(shell):
                shell = "cmd.exe"
            env = os.environ.copy()
            env.setdefault("TERM", "xterm-256color")
            try:
                proc = WinPtyProcess.spawn(
                    shell,
                    cwd=cwd if cwd and os.path.isdir(cwd) else None,
                    env=env,
                    dimensions=(rows, cols),
                    backend=1,
                )
            except TypeError:
                proc = WinPtyProcess.spawn(
                    shell,
                    cwd=cwd if cwd and os.path.isdir(cwd) else None,
                    env=env,
                    dimensions=(rows, cols),
                )
            # winpty 下 cmd.exe 有时不会主动吐出 prompt，先发一个回车触发首屏
            try:
                proc.write("\r")
            except Exception:
                pass
            _sessions[socket_sid][csid] = {"kind": "win", "proc": proc, "fd": None}
            t = threading.Thread(target=_reader_win, args=(socket_sid, csid, proc), daemon=True)
            t.start()
            _sessions[socket_sid][csid]["reader"] = t
            log.warning("[term] start_local_pty(win) ok sid=%s csid=%s", socket_sid, csid)
            return True, ""
        except Exception as e:
            log.exception("win pty spawn")
            return False, str(e)

    if _HAS_UNIX_PTY:
        try:
            master_fd = _unix_fork_pty(cwd, rows, cols)
            _sessions[socket_sid][csid] = {"kind": "unix", "proc": None, "fd": master_fd}
            t = threading.Thread(target=_reader_unix, args=(socket_sid, csid, master_fd), daemon=True)
            t.start()
            _sessions[socket_sid][csid]["reader"] = t
            return True, ""
        except Exception as e:
            log.exception("unix pty fork")
            return False, str(e)

    return False, "当前环境不支持本地 PTY（Windows 请 pip install pywinpty；Linux/macOS 需 pty）。"


def _start_ssh(socket_sid: str, csid: str, cols: int, rows: int, ssh_cfg: dict) -> tuple[bool, str]:
    if not _HAS_PARAMIKO or paramiko is None:
        return False, "未安装 paramiko，请 pip install paramiko"
    host = (ssh_cfg.get("host") or "").strip()
    port = int(ssh_cfg.get("port") or 22)
    username = (ssh_cfg.get("username") or "").strip()
    password = ssh_cfg.get("password") or ""
    key_text = (ssh_cfg.get("key_text") or "").strip() or None
    if not host or not username:
        return False, "SSH 需要 host 与 username"

    try:
        from io import StringIO

        cli = paramiko.SSHClient()
        cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        pkey = None
        if key_text:
            fp = StringIO(key_text)
            _loaders = [paramiko.RSAKey, paramiko.Ed25519Key]
            if hasattr(paramiko, "ECDSAKey"):
                _loaders.append(paramiko.ECDSAKey)
            for loader in _loaders:
                try:
                    fp.seek(0)
                    pkey = loader.from_private_key(fp, password=password or None)
                    break
                except Exception:
                    pkey = None
            if pkey is None:
                return False, "无法解析 SSH 私钥文本"
        kwargs = {
            "hostname": host,
            "port": port,
            "username": username,
            "timeout": 30,
            "allow_agent": False,
            "look_for_keys": False,
        }
        if pkey:
            kwargs["pkey"] = pkey
        if password:
            kwargs["password"] = password
        cli.connect(**kwargs)
        chan = cli.invoke_shell(term="xterm", width=cols, height=rows)
        _sessions[socket_sid][csid] = {"kind": "ssh", "chan": chan, "ssh_client": cli, "proc": None, "fd": None}
        t = threading.Thread(target=_reader_ssh, args=(socket_sid, csid, chan), daemon=True)
        t.start()
        _sessions[socket_sid][csid]["reader"] = t
        return True, ""
    except Exception as e:
        log.exception("ssh connect")
        return False, str(e)


def register_terminal_socket_handlers(socketio, app) -> None:
    global _socketio, _app
    _socketio = socketio
    _app = app

    @socketio.on("connect")
    def on_connect():
        if request.sid not in _sessions:
            _sessions[request.sid] = {}
        uid = _terminal_uid()
        log.warning("[term] socket connect sid=%s uid=%s headers=%s", request.sid, uid, dict(request.headers)[:500])
        return True

    @socketio.on("disconnect")
    def on_disconnect():
        _cleanup_socket(request.sid)

    @socketio.on("term_start")
    def on_term_start(data):
        uid = _terminal_uid()
        if uid is None:
            socketio.emit(
                "term_error",
                {
                    "ok": False,
                    "message": "终端需要登录态（请刷新页面或重新登录后再试）",
                    "client_session_id": (data or {}).get("client_session_id") or "default",
                },
                room=request.sid,
            )
            return
        try:
            payload0 = data or {}
            _csid0 = (payload0.get("client_session_id") or "default").strip() or "default"
        except Exception:
            _csid0 = "default"
        log.warning("[term] term_start received sid=%s uid=%s csid=%s", request.sid, uid, _csid0)
        socket_sid = request.sid
        payload = data or {}
        csid = (payload.get("client_session_id") or "default").strip() or "default"
        cols = int(payload.get("cols") or 80)
        rows = int(payload.get("rows") or 24)
        cwd = (payload.get("cwd") or "").strip() or None
        if cwd and not os.path.isdir(cwd):
            cwd = None
        mode = (payload.get("mode") or "local").strip().lower()
        project_id = payload.get("project_id")
        try:
            pid = int(project_id) if project_id is not None else None
        except (TypeError, ValueError):
            pid = None

        if socket_sid not in _sessions:
            _sessions[socket_sid] = {}

        # 已达上限且非替换自身
        if csid not in _sessions[socket_sid] and len(_sessions[socket_sid]) >= MAX_SESSIONS:
            socketio.emit(
                "term_error",
                {"ok": False, "message": f"最多同时 {MAX_SESSIONS} 个终端会话", "client_session_id": csid},
                room=socket_sid,
            )
            return

        _cleanup_one(socket_sid, csid)

        cols = max(20, min(cols, 500))
        rows = max(5, min(rows, 200))

        ok = False
        err = ""
        if mode == "ssh":
            ssh_cfg = payload.get("ssh") or {}
            ok, err = _start_ssh(socket_sid, csid, cols, rows, ssh_cfg if isinstance(ssh_cfg, dict) else {})
        else:
            ok, err = _start_local_pty(socket_sid, csid, cols, rows, cwd)

        detail = json.dumps({"mode": mode, "cwd": cwd, "csid": csid}, ensure_ascii=False)[:65000]

        _audit(app, uid, "term_start", detail, csid, pid)

        if ok:
            socketio.emit("term_started", {"ok": True, "client_session_id": csid}, room=socket_sid)
        else:
            socketio.emit(
                "term_error",
                {"ok": False, "message": err, "client_session_id": csid},
                room=socket_sid,
            )

    @socketio.on("term_close")
    def on_term_close(data):
        uid = _terminal_uid()
        if uid is None:
            return
        payload = data or {}
        csid = (payload.get("client_session_id") or "").strip()
        if not csid:
            return
        _cleanup_one(request.sid, csid)
        _audit(app, uid, "term_close", None, csid, None)

    @socketio.on("term_input")
    def on_term_input(data):
        if _terminal_uid() is None:
            return
        socket_sid = request.sid
        payload = data or {}
        csid = (payload.get("client_session_id") or "default").strip() or "default"
        bucket = _sessions.get(socket_sid) or {}
        info = bucket.get(csid)
        if not info:
            return
        b64 = payload.get("b64") or ""
        try:
            raw = base64.b64decode(b64)
        except Exception:
            return
        try:
            kind = info.get("kind")
            if kind == "win" and info.get("proc"):
                p = info["proc"]
                try:
                    p.write(raw)
                except TypeError:
                    # pywinpty 3 / winpty：write 接受 str
                    p.write(raw.decode("utf-8", errors="surrogateescape"))
            elif kind == "unix" and info.get("fd") is not None:
                os.write(info["fd"], raw)
            elif kind == "ssh" and info.get("chan"):
                info["chan"].send(raw)
        except Exception as e:
            log.debug("term_input: %s", e)

    @socketio.on("term_resize")
    def on_term_resize(data):
        if _terminal_uid() is None:
            return
        socket_sid = request.sid
        payload = data or {}
        csid = (payload.get("client_session_id") or "default").strip() or "default"
        bucket = _sessions.get(socket_sid) or {}
        info = bucket.get(csid)
        if not info:
            return
        cols = int(payload.get("cols") or 80)
        rows = int(payload.get("rows") or 24)
        cols = max(20, min(cols, 500))
        rows = max(5, min(rows, 200))
        try:
            kind = info.get("kind")
            if kind == "win" and info.get("proc"):
                p = info["proc"]
                if hasattr(p, "set_window_size"):
                    p.set_window_size(rows, cols)
                elif hasattr(p, "setwinsize"):
                    p.setwinsize(rows, cols)
            elif kind == "unix" and info.get("fd") is not None:
                _set_winsize_unix(info["fd"], rows, cols)
            elif kind == "ssh" and info.get("chan"):
                ch = info["chan"]
                if hasattr(ch, "resize_pty"):
                    ch.resize_pty(width=cols, height=rows)
        except Exception as e:
            log.debug("term_resize: %s", e)
