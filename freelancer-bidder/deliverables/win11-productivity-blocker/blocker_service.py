"""
Windows 11 Background Productivity Blocker
Bid project: Windows 11 Background Productivity Service

Blocks listed websites (hosts file) and applications (process kill loop).
Runs as a tray-friendly background process; optional NSSM/Task Scheduler install.

Usage (admin recommended for hosts edits):
  python blocker_service.py
  python blocker_service.py --config config.json
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

try:
    import psutil
except ImportError:  # pragma: no cover
    psutil = None

HOSTS_PATH = Path(r"C:\Windows\System32\drivers\etc\hosts")
MARKER_BEGIN = "# >>> PRODUCTIVITY-BLOCKER BEGIN"
MARKER_END = "# <<< PRODUCTIVITY-BLOCKER END"
DEFAULT_CONFIG = Path(__file__).with_name("config.json")


@dataclass
class Config:
    blocked_sites: list[str] = field(default_factory=list)
    blocked_apps: list[str] = field(default_factory=list)
    poll_seconds: float = 3.0
    redirect_ip: str = "127.0.0.1"

    @classmethod
    def load(cls, path: Path) -> "Config":
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            blocked_sites=[s.strip().lower() for s in data.get("blocked_sites", []) if s.strip()],
            blocked_apps=[a.strip().lower() for a in data.get("blocked_apps", []) if a.strip()],
            poll_seconds=float(data.get("poll_seconds", 3.0)),
            redirect_ip=str(data.get("redirect_ip", "127.0.0.1")),
        )


def is_admin() -> bool:
    try:
        import ctypes

        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def normalize_host(site: str) -> list[str]:
    site = site.lower().removeprefix("https://").removeprefix("http://").split("/")[0]
    hosts = {site}
    if site.startswith("www."):
        hosts.add(site[4:])
    else:
        hosts.add("www." + site)
    return sorted(hosts)


def apply_hosts_block(cfg: Config) -> None:
    if not HOSTS_PATH.exists():
        raise FileNotFoundError(HOSTS_PATH)

    original = HOSTS_PATH.read_text(encoding="utf-8", errors="ignore")
    lines = original.splitlines()
    kept: list[str] = []
    skipping = False
    for line in lines:
        if line.strip() == MARKER_BEGIN:
            skipping = True
            continue
        if line.strip() == MARKER_END:
            skipping = False
            continue
        if not skipping:
            kept.append(line)

    block_lines = [MARKER_BEGIN]
    for site in cfg.blocked_sites:
        for host in normalize_host(site):
            block_lines.append(f"{cfg.redirect_ip} {host}")
    block_lines.append(MARKER_END)

    new_text = "\n".join(kept).rstrip() + "\n\n" + "\n".join(block_lines) + "\n"
    HOSTS_PATH.write_text(new_text, encoding="utf-8")
    # flush DNS cache best-effort
    try:
        subprocess.run(["ipconfig", "/flushdns"], capture_output=True, check=False)
    except Exception:
        pass


def remove_hosts_block() -> None:
    if not HOSTS_PATH.exists():
        return
    original = HOSTS_PATH.read_text(encoding="utf-8", errors="ignore")
    lines = original.splitlines()
    kept: list[str] = []
    skipping = False
    for line in lines:
        if line.strip() == MARKER_BEGIN:
            skipping = True
            continue
        if line.strip() == MARKER_END:
            skipping = False
            continue
        if not skipping:
            kept.append(line)
    HOSTS_PATH.write_text("\n".join(kept).rstrip() + "\n", encoding="utf-8")
    try:
        subprocess.run(["ipconfig", "/flushdns"], capture_output=True, check=False)
    except Exception:
        pass


def kill_blocked_apps(cfg: Config) -> list[str]:
    if psutil is None:
        return []
    killed: list[str] = []
    targets = set(cfg.blocked_apps)
    for proc in psutil.process_iter(["pid", "name"]):
        try:
            name = (proc.info.get("name") or "").lower()
            if name in targets:
                proc.kill()
                killed.append(name)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return killed


def watch_loop(cfg: Config, stop: threading.Event) -> None:
    while not stop.is_set():
        killed = kill_blocked_apps(cfg)
        if killed:
            print(f"[block] killed: {', '.join(sorted(set(killed)))}")
        stop.wait(cfg.poll_seconds)


def write_default_config(path: Path) -> None:
    if path.exists():
        return
    sample = {
        "blocked_sites": ["facebook.com", "twitter.com", "tiktok.com", "reddit.com"],
        "blocked_apps": ["discord.exe", "steam.exe"],
        "poll_seconds": 3,
        "redirect_ip": "127.0.0.1",
    }
    path.write_text(json.dumps(sample, indent=2), encoding="utf-8")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Win11 productivity blocker")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--uninstall-hosts", action="store_true", help="Remove hosts entries and exit")
    parser.add_argument("--once", action="store_true", help="Apply hosts + one app sweep, then exit")
    args = parser.parse_args(argv)

    write_default_config(args.config)

    if args.uninstall_hosts:
        if not is_admin():
            print("[warn] Admin rights recommended to edit hosts.", file=sys.stderr)
        remove_hosts_block()
        print("Hosts block removed.")
        return

    cfg = Config.load(args.config)
    print(f"Loaded config: {args.config}")
    print(f"Sites={len(cfg.blocked_sites)} Apps={len(cfg.blocked_apps)}")

    if not is_admin():
        print("[warn] Not running as Administrator — hosts edits may fail.", file=sys.stderr)

    try:
        apply_hosts_block(cfg)
        print("Hosts block applied.")
    except PermissionError:
        print("[error] Cannot write hosts file. Re-run as Administrator.", file=sys.stderr)
    except Exception as exc:
        print(f"[error] hosts update failed: {exc}", file=sys.stderr)

    if args.once:
        killed = kill_blocked_apps(cfg)
        print(f"App sweep done. killed={killed}")
        return

    if psutil is None:
        print("[error] psutil missing. pip install psutil", file=sys.stderr)
        sys.exit(1)

    stop = threading.Event()
    print("Watching blocked apps. Ctrl+C to stop (hosts stay until --uninstall-hosts).")
    try:
        watch_loop(cfg, stop)
    except KeyboardInterrupt:
        stop.set()
        print("\nStopped watcher. Hosts still blocked; run with --uninstall-hosts to clear.")


if __name__ == "__main__":
    main()
