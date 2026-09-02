"""One-off deploy helper. Password via VMISS_PASS env only."""

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


def connect(password: str, retries: int = 6) -> paramiko.SSHClient:
    last: Exception | None = None
    for i in range(retries):
        try:
            sock = socket.create_connection((HOST, 22), timeout=30)
            transport = paramiko.Transport(sock)
            transport.banner_timeout = 120
            transport.auth_timeout = 120
            transport.start_client(timeout=120)
            transport.auth_password("root", password)
            client = paramiko.SSHClient()
            client._transport = transport
            print(f"connected (try {i + 1})")
            return client
        except Exception as exc:  # noqa: BLE001
            last = exc
            print(f"retry {i + 1}: {type(exc).__name__}: {exc}")
            time.sleep(3 * (i + 1))
    raise RuntimeError(f"SSH failed: {last}")


def run(client: paramiko.SSHClient, cmd: str, timeout: int = 240) -> tuple[int, str]:
    print(">>>", cmd.replace("\n", " ")[:140])
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
    print(text[-3000:])
    print("RC", code)
    return code, text


def upload(client: paramiko.SSHClient) -> None:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for p in LOCAL.rglob("*"):
            if not p.is_file():
                continue
            rel = p.relative_to(LOCAL).as_posix()
            if any(x in rel for x in ("__pycache__", ".venv", ".ipynb_checkpoints", "_deploy_vps.py")):
                continue
            tar.add(p, arcname=f"data-heuristics-optimizer/{rel}")
    buf.seek(0)
    sftp = client.open_sftp()
    with sftp.file("/tmp/heuristics-demo.tgz", "wb") as rf:
        rf.write(buf.read())
    sftp.close()
    print("uploaded tarball")


def main() -> None:
    password = os.environ.get("VMISS_PASS")
    if not password:
        raise SystemExit("Set VMISS_PASS env var")

    client = connect(password)
    upload(client)

    steps = [
        (
            "mkdir -p /opt && rm -rf /opt/data-heuristics-optimizer && "
            "tar -xzf /tmp/heuristics-demo.tgz -C /opt && ls /opt/data-heuristics-optimizer",
            90,
        ),
        (
            "cd /opt/data-heuristics-optimizer && python3 -m venv .venv && "
            ". .venv/bin/activate && pip install -U pip && pip install -r requirements.txt",
            300,
        ),
        (
            """cat >/etc/systemd/system/heuristics-demo.service <<'EOF'
[Unit]
Description=Data Heuristics Optimizer Demo
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/data-heuristics-optimizer
ExecStart=/opt/data-heuristics-optimizer/.venv/bin/uvicorn app:app --host 0.0.0.0 --port 8080
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable --now heuristics-demo.service
systemctl restart heuristics-demo.service
iptables -I INPUT -p tcp --dport 8080 -j ACCEPT 2>/dev/null || true
sleep 2
systemctl --no-pager status heuristics-demo | head -n 20
curl -sS http://127.0.0.1:8080/api/metrics
echo
""",
            120,
        ),
    ]

    for cmd, timeout in steps:
        code, _ = run(client, cmd, timeout=timeout)
        if code != 0:
            client.close()
            raise SystemExit(code)

    client.close()
    print("DEPLOY OK -> http://45.221.112.16:8080/")


if __name__ == "__main__":
    main()
