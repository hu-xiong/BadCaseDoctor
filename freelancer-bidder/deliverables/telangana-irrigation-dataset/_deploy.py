"""Deploy Telangana SAMPLE preview to VPS port 8001. Password: VMISS_PASS env."""

from __future__ import annotations

import io
import os
import socket
import tarfile
import time
from pathlib import Path

import paramiko

HOST = "45.221.112.16"
LOCAL = Path(__file__).resolve().parent


def connect(password: str) -> paramiko.SSHClient:
    last: Exception | None = None
    for i in range(6):
        try:
            sock = socket.create_connection((HOST, 22), timeout=30)
            t = paramiko.Transport(sock)
            t.banner_timeout = 120
            t.auth_timeout = 120
            t.start_client(timeout=120)
            t.auth_password("root", password)
            c = paramiko.SSHClient()
            c._transport = t
            print("connected", i + 1)
            return c
        except Exception as exc:  # noqa: BLE001
            last = exc
            print("retry", i + 1, exc)
            time.sleep(4)
    raise RuntimeError(str(last))


def run(client: paramiko.SSHClient, cmd: str, timeout: int = 240) -> tuple[int, str]:
    print(">>>", cmd.replace("\n", " ")[:120])
    chan = client.get_transport().open_session()
    chan.settimeout(timeout)
    chan.exec_command(cmd)
    out = b""
    err = b""
    while True:
        if chan.recv_ready():
            out += chan.recv(65535)
        if chan.recv_stderr_ready():
            err += chan.recv_stderr(65535)
        if chan.exit_status_ready():
            while chan.recv_ready():
                out += chan.recv(65535)
            while chan.recv_stderr_ready():
                err += chan.recv_stderr(65535)
            break
        time.sleep(0.2)
    code = chan.recv_exit_status()
    text = (out + err).decode("utf-8", "replace")
    print(text[-2500:])
    print("RC", code)
    return code, text


def main() -> None:
    password = os.environ["VMISS_PASS"]
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for p in LOCAL.rglob("*"):
            if not p.is_file():
                continue
            rel = p.relative_to(LOCAL).as_posix()
            if any(x in rel for x in ("__pycache__", ".venv", "_deploy.py")):
                continue
            tar.add(p, arcname=f"telangana-irrigation-dataset/{rel}")
    buf.seek(0)

    client = connect(password)
    sftp = client.open_sftp()
    with sftp.file("/tmp/telangana-sample.tgz", "wb") as rf:
        rf.write(buf.read())
    sftp.close()
    print("uploaded")

    steps = [
        (
            "mkdir -p /opt && rm -rf /opt/telangana-irrigation-dataset && "
            "tar -xzf /tmp/telangana-sample.tgz -C /opt && ls /opt/telangana-irrigation-dataset",
            60,
        ),
        (
            "cd /opt/telangana-irrigation-dataset && python3 -m venv .venv && "
            ". .venv/bin/activate && pip install -U pip && pip install -r requirements.txt",
            240,
        ),
        (
            r"""
cat >/etc/systemd/system/telangana-sample.service <<'EOF'
[Unit]
Description=Telangana Irrigation SAMPLE Preview
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/telangana-irrigation-dataset
Environment=PYTHONUNBUFFERED=1
ExecStart=/opt/telangana-irrigation-dataset/.venv/bin/uvicorn app:app --host 0.0.0.0 --port 8001
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable --now telangana-sample.service
systemctl restart telangana-sample.service
iptables -I INPUT -p tcp --dport 8001 -j ACCEPT 2>/dev/null || true
sleep 2
systemctl --no-pager status telangana-sample | head -n 20
curl -sS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8001/
""",
            90,
        ),
    ]
    for cmd, timeout in steps:
        code, _ = run(client, cmd, timeout=timeout)
        if code != 0:
            client.close()
            raise SystemExit(code)
    client.close()
    print("OK http://45.221.112.16:8001/")


if __name__ == "__main__":
    main()
