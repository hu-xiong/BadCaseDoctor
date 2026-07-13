# badcase_sdk/text_export.py
"""
将 Prometheus 注册表导出为文本，便于本地排查或整份交给 AI 分析。

环境变量：
- BADCASE_METRICS_TEXT_DIR：输出目录，默认 <项目根>/observability/prometheus
- BADCASE_METRICS_TEXT_INTERVAL：后台落盘间隔秒，0 表示不启动后台线程
"""
from __future__ import annotations

import atexit
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from prometheus_client import REGISTRY, generate_latest

_writer_lock = threading.Lock()
_bg_thread: Optional[threading.Thread] = None
_bg_stop = threading.Event()


def _default_out_dir() -> Path:
    env = (os.getenv("BADCASE_METRICS_TEXT_DIR") or "").strip()
    if env:
        return Path(env).expanduser().resolve()
    # sdk/badcase_sdk -> sdk -> repo root
    root = Path(__file__).resolve().parents[2]
    return root / "observability" / "prometheus"


def collect_metric_samples(registry=REGISTRY) -> List[Dict[str, Any]]:
    """从注册表收集样本（比手解析 .prom 文本更稳）。"""
    rows: List[Dict[str, Any]] = []
    for family in registry.collect():
        for sample in family.samples:
            rows.append(
                {
                    "name": sample.name,
                    "labels": dict(sample.labels),
                    "value": float(sample.value),
                }
            )
    rows.sort(key=lambda r: (r["name"], str(r["labels"])))
    return rows


def format_samples_summary(
    samples: List[Dict[str, Any]],
    *,
    skip_zero_counters: bool = True,
    max_lines: int = 5000,
) -> str:
    """生成给 AI / 人读的紧凑摘要。"""
    lines: List[str] = []
    for row in samples:
        name = row["name"]
        val = row["value"]
        if skip_zero_counters and name.endswith("_total") and val == 0.0:
            continue
        if skip_zero_counters and name.endswith("_created") and val == 0.0:
            continue
        labels = row.get("labels") or {}
        if labels:
            lab = ",".join(f'{k}="{v}"' for k, v in sorted(labels.items()))
            lines.append(f"{name}{{{lab}}} {val}")
        else:
            lines.append(f"{name} {val}")
        if len(lines) >= max_lines:
            lines.append(f"... truncated, total_samples={len(samples)}")
            break
    return "\n".join(lines)


def write_snapshot(
    out_dir: Optional[os.PathLike] = None,
    *,
    registry=REGISTRY,
    prefix: str = "metrics",
) -> Tuple[Path, Path]:
    """
    写入两份文件：
    - metrics_latest.prom：Prometheus  exposition 格式（可被 promtool 解析）
    - metrics_latest_summary.txt：扁平摘要（适合贴给 AI）
    返回 (prom_path, summary_path)。
    """
    base = Path(out_dir or _default_out_dir())
    base.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    prom_path = base / f"{prefix}_latest.prom"
    summary_path = base / f"{prefix}_latest_summary.txt"
    stamped_prom = base / f"{prefix}_{ts}.prom"
    stamped_summary = base / f"{prefix}_{ts}_summary.txt"

    prom_bytes = generate_latest(registry)
    samples = collect_metric_samples(registry)
    summary_text = format_samples_summary(samples)

    header = (
        f"# badcase_sdk text export utc={ts}\n"
        f"# samples={len(samples)}\n\n"
    )
    with _writer_lock:
        prom_path.write_bytes(prom_bytes)
        summary_path.write_text(header + summary_text, encoding="utf-8")
        stamped_prom.write_bytes(prom_bytes)
        stamped_summary.write_text(header + summary_text, encoding="utf-8")

    return prom_path, summary_path


def start_periodic_export(
    interval_sec: Optional[float] = None,
    out_dir: Optional[os.PathLike] = None,
) -> bool:
    """启动守护线程定期落盘；已启动则忽略。返回是否已启动。"""
    global _bg_thread
    if interval_sec is None:
        try:
            interval_sec = float(os.getenv("BADCASE_METRICS_TEXT_INTERVAL", "60"))
        except (TypeError, ValueError):
            interval_sec = 60.0
    if interval_sec <= 0:
        return False
    if _bg_thread is not None and _bg_thread.is_alive():
        return False

    def _loop() -> None:
        while not _bg_stop.wait(interval_sec):
            try:
                write_snapshot(out_dir)
            except Exception:
                pass

    _bg_thread = threading.Thread(
        target=_loop, name="badcase-metrics-text-export", daemon=True
    )
    _bg_thread.start()
    atexit.register(stop_periodic_export)
    return True


def stop_periodic_export() -> None:
    _bg_stop.set()
