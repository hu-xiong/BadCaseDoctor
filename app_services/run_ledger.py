# -*- coding: utf-8 -*-
"""工具长任务通用台账（run_ledger）。

任何工具派生的长任务（Midscene 探测、WebFetch 调研……）统一开账，断点可续：

    run_id = start("midscene_explore", goal, user_id=u, project_id=p, chat_session_id=s)
    write_step(run_id, {"entry": "登录", "status": "pass", "ms": 1200})
    save_checkpoint(run_id, {"entries": [...]})      # 原子写 + 即时同步 MinIO
    finish(run_id, "interrupted", counts={"pass": 3, "fail": 1})
    latest_interrupted(user_id=u, project_id=p, chat_session_id=s, tool_kind="midscene_explore")

存储三层：
    本地热写  <repo>/tmp/runs/<user_id>/<project_id>/<chat_session_id>/<run_id>/
              meta.json / checkpoint.json / steps.jsonl / artifacts/
    MinIO 冷存  <MINIO_SAAS_FILE_PATH><RUN_LEDGER_MINIO_SUBPREFIX>/<user>/<project>/<session>/<run_id>/
              checkpoint.json 每次 save 即时同步；全量（含 steps.jsonl/artifacts）在 finish 时同步
    MySQL 索引  tool_runs 表（鉴权查询 + 会话任务链，prev_run_id 串联前后任务）

幂等/原子：checkpoint/meta 均 .tmp+rename 原子写；finish 对已终态 run_id 直接返回不重复收尾。
DB 与 MinIO 均为 best-effort：失败只记日志，绝不影响工具主流程。

安全红线：meta/checkpoint/steps/artifacts 绝不写入密码、密钥、token —— 只存路径与描述。
"""
from __future__ import annotations

import json
import mimetypes
import os
import uuid
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Dict, List, Optional

from config import Config
from db_extensions import db
from models.orm import ToolRun

TERMINAL_STATUSES = frozenset({"success", "failed", "cancelled", "interrupted"})

_OPEN_RUN_DIRS: Dict[str, str] = {}


def _log(msg: str) -> None:
    try:
        print(msg, flush=True)
    except Exception:
        pass


def _utcnow() -> datetime:
    return datetime.utcnow()


def _local_root() -> str:
    root = (Config.RUN_LEDGER_LOCAL_ROOT or "tmp/runs").strip().strip("/")
    if os.path.isabs(root):
        return root
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, root)


def _seg(value: Optional[int]) -> str:
    return "0" if value is None else str(value)


def run_dir(user_id: int, project_id: Optional[int], chat_session_id: Optional[int], run_id: str) -> str:
    return os.path.join(_local_root(), str(user_id), _seg(project_id), _seg(chat_session_id), run_id)


def minio_prefix_for(user_id: int, project_id: Optional[int], chat_session_id: Optional[int], run_id: str) -> str:
    sub = (Config.RUN_LEDGER_MINIO_SUBPREFIX or "runs").strip().strip("/") or "runs"
    parts = [
        (Config.MINIO_SAAS_FILE_PATH or "").strip().strip("/"),
        sub,
        str(user_id),
        _seg(project_id),
        _seg(chat_session_id),
        run_id,
    ]
    return "/".join(p for p in parts if p) + "/"


def _atomic_write_bytes(path: str, data: bytes) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, path)


def _atomic_write_json(path: str, data: Any) -> None:
    _atomic_write_bytes(path, json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8"))


def _read_json(path: str) -> Optional[Any]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


@contextmanager
def _app_ctx():
    try:
        from app import app as _app
    except Exception:
        _app = None
    if _app is not None:
        with _app.app_context():
            yield
    else:
        yield


def _db_index(run_id: str, **fields) -> None:
    """best-effort 写 tool_runs 索引行；失败只记日志，文件台账不受影响。"""
    try:
        with _app_ctx():
            row = db.session.get(ToolRun, run_id)
            if row is None:
                row = ToolRun(run_id=run_id)
                db.session.add(row)
            for k, v in fields.items():
                setattr(row, k, v)
            db.session.commit()
    except Exception as e:
        try:
            db.session.rollback()
        except Exception:
            pass
        _log(f"[run_ledger] tool_runs 索引写入失败（文件台账不受影响）: {e}")


def _resolve_dir(run_id: str, user_id: Optional[int] = None,
                 project_id: Optional[int] = None, chat_session_id: Optional[int] = None) -> Optional[str]:
    rd = _OPEN_RUN_DIRS.get(run_id)
    if rd and os.path.isdir(rd):
        return rd
    if user_id is not None:
        rd = run_dir(user_id, project_id, chat_session_id, run_id)
        if os.path.isdir(rd):
            return rd
    root = _local_root()
    if os.path.isdir(root):
        for u in os.listdir(root):
            pu = os.path.join(root, u)
            if not os.path.isdir(pu):
                continue
            for p in os.listdir(pu):
                pp = os.path.join(pu, p)
                if not os.path.isdir(pp):
                    continue
                for s in os.listdir(pp):
                    cand = os.path.join(pp, s, run_id)
                    if os.path.isdir(cand):
                        return cand
    return None


# ---------------------------------------------------------------- 四个原语

def start(tool_kind: str, goal: str, *, user_id: int, project_id: Optional[int] = None,
          chat_session_id: Optional[int] = None, prev_run_id: Optional[str] = None,
          extra_meta: Optional[Dict[str, Any]] = None) -> str:
    """开账：建四层隔离目录 + meta/checkpoint/steps 骨架 + DB 索引行，返回 run_id。"""
    run_id = str(uuid.uuid4())
    rd = run_dir(user_id, project_id, chat_session_id, run_id)
    os.makedirs(os.path.join(rd, "artifacts"), exist_ok=True)
    meta: Dict[str, Any] = {
        "run_id": run_id,
        "tool_kind": tool_kind,
        "goal": goal,
        "user_id": user_id,
        "project_id": project_id,
        "chat_session_id": chat_session_id,
        "prev_run_id": prev_run_id,
        "status": "running",
        "counts": {},
        "created_at": _utcnow().isoformat(),
        "finished_at": None,
    }
    if extra_meta:
        meta["extra"] = extra_meta
    _atomic_write_json(os.path.join(rd, "meta.json"), meta)
    _atomic_write_json(os.path.join(rd, "checkpoint.json"), {"entries": [], "updated_at": meta["created_at"]})
    open(os.path.join(rd, "steps.jsonl"), "a", encoding="utf-8").close()
    _OPEN_RUN_DIRS[run_id] = rd
    _db_index(run_id, user_id=user_id, project_id=project_id, chat_session_id=chat_session_id,
              tool_kind=tool_kind, goal=goal, status="running", prev_run_id=prev_run_id)
    return run_id


def write_step(run_id: str, step: Dict[str, Any], *, user_id: Optional[int] = None,
               project_id: Optional[int] = None, chat_session_id: Optional[int] = None) -> bool:
    """追加一条执行步到 steps.jsonl（本地热写，finish 时整体同步 MinIO）。"""
    rd = _resolve_dir(run_id, user_id, project_id, chat_session_id)
    if rd is None:
        return False
    record = dict(step)
    record.setdefault("ts", _utcnow().isoformat())
    with open(os.path.join(rd, "steps.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return True


def save_checkpoint(run_id: str, data: Any, *, sync_minio: bool = True,
                    user_id: Optional[int] = None, project_id: Optional[int] = None,
                    chat_session_id: Optional[int] = None) -> bool:
    """原子覆盖 checkpoint.json 并即时同步 MinIO（S3 小文件整覆，断点跨机可拉）。"""
    rd = _resolve_dir(run_id, user_id, project_id, chat_session_id)
    if rd is None:
        return False
    payload = dict(data) if isinstance(data, dict) else {"data": data}
    payload.setdefault("run_id", run_id)
    payload["updated_at"] = _utcnow().isoformat()
    _atomic_write_json(os.path.join(rd, "checkpoint.json"), payload)
    if sync_minio:
        sync_checkpoint_to_minio(run_id, rd=rd)
    return True


def finish(run_id: str, status: str, *, counts: Optional[Dict[str, Any]] = None,
           summary: Optional[str] = None, user_id: Optional[int] = None,
           project_id: Optional[int] = None, chat_session_id: Optional[int] = None) -> str:
    """收尾：幂等（已终态直接返回）；写 meta 终态 + 全量同步 MinIO + 更新 DB 索引。"""
    rd = _resolve_dir(run_id, user_id, project_id, chat_session_id)
    meta: Dict[str, Any] = {}
    if rd is not None:
        meta = _read_json(os.path.join(rd, "meta.json")) or {}
    if meta.get("status") in TERMINAL_STATUSES:
        return meta["status"]
    if status not in TERMINAL_STATUSES:
        status = "failed"
    meta.update({
        "run_id": run_id,
        "status": status,
        "counts": counts if counts is not None else (meta.get("counts") or {}),
        "summary": summary if summary is not None else meta.get("summary"),
        "finished_at": _utcnow().isoformat(),
    })
    prefix = minio_prefix_for(
        meta.get("user_id") if meta.get("user_id") is not None else (user_id if user_id is not None else 0),
        meta.get("project_id", project_id),
        meta.get("chat_session_id", chat_session_id),
        run_id,
    )
    if rd is not None:
        _atomic_write_json(os.path.join(rd, "meta.json"), meta)
        sync_to_minio(run_id, rd=rd)
    _db_index(run_id, status=status, counts_json=meta.get("counts") or {},
              summary=meta.get("summary"), finished_at=_utcnow(), minio_prefix=prefix)
    _OPEN_RUN_DIRS.pop(run_id, None)
    return status


# ---------------------------------------------------------------- MinIO 同步

def _minio_client_or_none():
    try:
        from app_services.minio_storage import get_minio_client, ensure_bucket_exists
        if not ensure_bucket_exists():
            return None
        return get_minio_client()
    except Exception as e:
        _log(f"[run_ledger] MinIO 客户端不可用: {e}")
        return None


def _upload_file(client, prefix: str, rd: str, rel: str) -> bool:
    path = os.path.join(rd, rel)
    if not os.path.isfile(path):
        return False
    key = prefix + rel.replace(os.sep, "/")
    ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
    try:
        with open(path, "rb") as f:
            client.upload_fileobj(f, Config.MINIO_BUCKET_NAME, key, ExtraArgs={"ContentType": ctype})
        return True
    except Exception as e:
        _log(f"[run_ledger] MinIO 上传失败 {key}: {e}")
        return False


def _prefix_from_meta(rd: str, run_id: str) -> str:
    meta = _read_json(os.path.join(rd, "meta.json")) or {}
    return minio_prefix_for(meta.get("user_id") or 0, meta.get("project_id"), meta.get("chat_session_id"), run_id)


def sync_checkpoint_to_minio(run_id: str, rd: Optional[str] = None) -> Optional[str]:
    rd = rd or _resolve_dir(run_id)
    if rd is None:
        return None
    client = _minio_client_or_none()
    if client is None:
        return None
    prefix = _prefix_from_meta(rd, run_id)
    _upload_file(client, prefix, rd, "checkpoint.json")
    return prefix


def sync_to_minio(run_id: str, rd: Optional[str] = None) -> Optional[str]:
    """整目录同步（meta/checkpoint/steps.jsonl/artifacts），返回 MinIO 前缀；失败返回 None。"""
    rd = rd or _resolve_dir(run_id)
    if rd is None:
        return None
    client = _minio_client_or_none()
    if client is None:
        return None
    prefix = _prefix_from_meta(rd, run_id)
    for root, _dirs, files in os.walk(rd):
        for name in files:
            rel = os.path.relpath(os.path.join(root, name), rd)
            _upload_file(client, prefix, rd, rel)
    return prefix


def ensure_local(run_id: str, *, user_id: Optional[int] = None,
                 project_id: Optional[int] = None, chat_session_id: Optional[int] = None) -> Optional[str]:
    """本地缺目录时从 MinIO 拉回（换机/清盘续跑），返回本地目录。"""
    rd = _resolve_dir(run_id, user_id, project_id, chat_session_id)
    if rd is not None and os.path.isfile(os.path.join(rd, "meta.json")):
        return rd
    client = _minio_client_or_none()
    if client is None:
        return None
    uid = user_id if user_id is not None else 0
    prefix = minio_prefix_for(uid, project_id, chat_session_id, run_id)
    rd = run_dir(uid, project_id, chat_session_id, run_id)
    found = False
    try:
        paginator = client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=Config.MINIO_BUCKET_NAME, Prefix=prefix):
            for obj in page.get("Contents", []):
                rel = obj["Key"][len(prefix):]
                if not rel:
                    continue
                dest = os.path.join(rd, rel.replace("/", os.sep))
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                resp = client.get_object(Bucket=Config.MINIO_BUCKET_NAME, Key=obj["Key"])
                try:
                    data = resp["Body"].read()
                finally:
                    try:
                        resp["Body"].close()
                    except Exception:
                        pass
                with open(dest, "wb") as f:
                    f.write(data)
                found = True
        return rd if found else None
    except Exception as e:
        _log(f"[run_ledger] 从 MinIO 拉取台账失败 {run_id}: {e}")
        return None


# ---------------------------------------------------------------- 读取 / 续跑

def read_steps(run_id: str, rd: Optional[str] = None, tail: int = 0) -> List[Dict[str, Any]]:
    rd = rd or _resolve_dir(run_id)
    if rd is None:
        return []
    path = os.path.join(rd, "steps.jsonl")
    if not os.path.isfile(path):
        return []
    out: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:
                continue
    return out[-tail:] if tail else out


def read_checkpoint(run_id: str, rd: Optional[str] = None) -> Optional[Dict[str, Any]]:
    rd = rd or _resolve_dir(run_id)
    if rd is None:
        return None
    return _read_json(os.path.join(rd, "checkpoint.json"))


def latest_interrupted(*, user_id: int, project_id: Optional[int] = None,
                       chat_session_id: Optional[int] = None,
                       tool_kind: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """找最近一个中断/未完成的本会话任务，本地缺则从 MinIO 拉回，供下一轮对话续作。"""
    row = None
    try:
        with _app_ctx():
            q = ToolRun.query.filter(
                ToolRun.user_id == user_id,
                ToolRun.status.in_(["interrupted", "running"]),
            )
            if project_id is not None:
                q = q.filter(ToolRun.project_id == project_id)
            if chat_session_id is not None:
                q = q.filter(ToolRun.chat_session_id == chat_session_id)
            if tool_kind:
                q = q.filter(ToolRun.tool_kind == tool_kind)
            row = q.order_by(ToolRun.created_at.desc()).first()
    except Exception as e:
        _log(f"[run_ledger] 查询中断任务失败: {e}")
        return None
    if row is None:
        return None
    rd = ensure_local(row.run_id, user_id=row.user_id, project_id=row.project_id,
                      chat_session_id=row.chat_session_id)
    return {
        "run_id": row.run_id,
        "status": row.status,
        "tool_kind": row.tool_kind,
        "goal": row.goal,
        "dir": rd,
        "checkpoint": read_checkpoint(row.run_id, rd=rd) if rd else None,
        "steps_tail": read_steps(row.run_id, rd=rd, tail=20) if rd else [],
        "minio_prefix": row.minio_prefix,
    }
