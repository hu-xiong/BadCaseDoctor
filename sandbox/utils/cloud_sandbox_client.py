from __future__ import annotations

import json
import mimetypes
import os
import time
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
from urllib import request as urllib_request
from urllib.error import HTTPError, URLError


@dataclass
class CloudSandboxHttpConfig:
    base_url: str
    token: str = ""
    tenant_id: str = ""
    timeout_s: int = 60

    @staticmethod
    def from_env() -> "CloudSandboxHttpConfig":
        def _to_int(v: str, default: int) -> int:
            try:
                return int(v)
            except Exception:
                return default

        # 如果环境变量未配置，默认使用当前云端沙箱地址，方便本地直接跑通
        default_base_url = "http://117.72.33.38:5000"

        return CloudSandboxHttpConfig(
            base_url=(os.getenv("SANDBOX_REMOTE_URL", "") or default_base_url).rstrip("/"),
            token=os.getenv("SANDBOX_REMOTE_TOKEN", "") or "",
            tenant_id=os.getenv("SANDBOX_TENANT_ID", "") or "",
            timeout_s=_to_int(os.getenv("SANDBOX_REMOTE_TIMEOUT_S", "60"), 60),
        )


def _headers(cfg: CloudSandboxHttpConfig) -> Dict[str, str]:
    h = {}
    if cfg.token:
        h["Authorization"] = f"Bearer {cfg.token}"
    if cfg.tenant_id:
        h["X-Tenant-Id"] = cfg.tenant_id
    return h


def _request_json(
    cfg: CloudSandboxHttpConfig,
    method: str,
    path: str,
    body_bytes: Optional[bytes] = None,
    headers: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    if not cfg.base_url:
        raise RuntimeError("SANDBOX_REMOTE_URL 未配置")
    url = f"{cfg.base_url}{path}"
    req_headers = headers.copy() if headers else {}
    req_headers.update(_headers(cfg))
    req = urllib_request.Request(url=url, data=body_bytes, headers=req_headers, method=method.upper())
    try:
        with urllib_request.urlopen(req, timeout=cfg.timeout_s) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return json.loads(raw) if raw else {}
    except HTTPError as e:
        raw = ""
        try:
            raw = e.read().decode("utf-8", errors="replace")
        except Exception:
            pass
        raise RuntimeError(f"云端沙盒 HTTP 错误: {e.code} {e.reason} {raw}".strip())
    except URLError as e:
        raise RuntimeError(f"云端沙盒连接失败: {e}")


def healthz(cfg: CloudSandboxHttpConfig) -> Dict[str, Any]:
    return _request_json(cfg, "GET", "/healthz")


def _encode_multipart_file(field_name: str, filename: str, file_bytes: bytes) -> Tuple[bytes, str]:
    boundary = f"----BadCaseDoctorBoundary{uuid.uuid4().hex}"
    content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"

    parts = []
    parts.append(f"--{boundary}\r\n".encode("utf-8"))
    parts.append(
        (
            f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"\r\n'
            f"Content-Type: {content_type}\r\n\r\n"
        ).encode("utf-8")
    )
    parts.append(file_bytes)
    parts.append(b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode("utf-8"))
    body = b"".join(parts)
    return body, f"multipart/form-data; boundary={boundary}"


def upload_sqlite_db_and_switch(
    cfg: CloudSandboxHttpConfig,
    db_path: str,
    filename: Optional[str] = None,
) -> Dict[str, Any]:
    if not os.path.exists(db_path):
        raise FileNotFoundError(db_path)

    with open(db_path, "rb") as f:
        data = f.read()

    fname = filename or os.path.basename(db_path) or "db.sqlite"
    body, ctype = _encode_multipart_file("file", fname, data)
    headers = {"Content-Type": ctype}
    return _request_json(cfg, "POST", "/api/v1/db/sync", body_bytes=body, headers=headers)


def _job_status(cfg: CloudSandboxHttpConfig, job_id: str) -> Dict[str, Any]:
    return _request_json(cfg, "GET", f"/api/v1/jobs/{job_id}")


def execute_sql(
    cfg: CloudSandboxHttpConfig,
    sql: str,
    timeout_ms: int = 30000,
    poll_interval_s: float = 0.5,
) -> Dict[str, Any]:
    """
    在云端沙箱上执行只读 SQL（使用沙箱内的 current.db 副本），同步轮询直到完成。

    Returns:
        {
            "success": bool,
            "data": List[Dict],
            "columns": List[str],
            "row_count": int,
            "sql": str,
            "error": str | None,
            "execution_mode": "cloud_sandbox",
        }
    """
    payload = {
        "sql": sql,
        "db": {"type": "sqlite"},
    }
    body = json.dumps({
        "task_type": "sql_readonly",
        "payload": payload,
        "timeout_ms": timeout_ms,
    }).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    out = _request_json(cfg, "POST", "/api/v1/execute", body_bytes=body, headers=headers)
    job_id = out.get("job_id")
    if not job_id:
        return {
            "success": False,
            "data": [],
            "columns": [],
            "row_count": 0,
            "sql": sql,
            "error": "云端未返回 job_id",
            "execution_mode": "cloud_sandbox",
        }

    deadline = time.time() + (timeout_ms / 1000.0) + 5.0
    while time.time() < deadline:
        status_resp = _job_status(cfg, job_id)
        status = (status_resp.get("status") or "").strip().lower()
        if status == "succeeded":
            result = status_resp.get("result") or {}
            return {
                "success": True,
                "data": result.get("data") or [],
                "columns": result.get("columns") or [],
                "row_count": result.get("row_count", 0),
                "sql": sql,
                "error": None,
                "execution_mode": "cloud_sandbox",
            }
        if status == "failed":
            err = status_resp.get("error") or "execution failed"
            return {
                "success": False,
                "data": [],
                "columns": [],
                "row_count": 0,
                "sql": sql,
                "error": err,
                "execution_mode": "cloud_sandbox",
            }
        time.sleep(poll_interval_s)

    return {
        "success": False,
        "data": [],
        "columns": [],
        "row_count": 0,
        "sql": sql,
        "error": "云端执行超时",
        "execution_mode": "cloud_sandbox",
    }


def cleanup_remote(
    cfg: CloudSandboxHttpConfig,
    keep_last: int = 10,
    max_age_hours: int = 72,
    all_tenants: bool = False,
) -> Dict[str, Any]:
    """
    调用云端沙箱 POST /api/v1/db/cleanup，按策略清理历史 DB 版本。

    - keep_last: 每租户保留最近 N 个版本（默认 10）
    - max_age_hours: 删除超过 N 小时的旧版本（默认 72）
    - all_tenants: True 时清理所有租户（需云端开启鉴权）

    Returns:
        {"success": True, "results": [{"tenant_id", "deleted", "errors", "kept"}, ...]}
        或抛 RuntimeError
    """
    body = json.dumps({
        "keep_last": max(1, int(keep_last)),
        "max_age_hours": max(0, int(max_age_hours)),
        "all_tenants": bool(all_tenants),
    }).encode("utf-8")
    return _request_json(cfg, "POST", "/api/v1/db/cleanup", body_bytes=body, headers={"Content-Type": "application/json"})

