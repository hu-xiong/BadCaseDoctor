"""未计划脏数据：检索过滤登记 + Redis 队列异步清理。

链路：
  1) grep 过滤未计划记录（plan_id 为空）→ record_unplanned_dirty(project_id, entity, id)
  2) 总任务完成（routers/agent.py run_async_loop finally）
     → flush_unplanned_to_queue(project_id)：登记项去重后 RPUSH 到 Redis 队列
  3) 后端 worker（app.py 启动时 daemon 线程，BRPOP 消费）
     → 二次校验「记录仍存在且 plan_id 仍为空」→ 物理删除：
       评论 + 仅被其引用的关联卡片 + CardPlanRelation + 记录本身，
       同步删除 ES 索引并失效项目缓存。

环境变量：
  DIRTY_CLEANUP_ENABLED=1               总开关（0 关闭入队与消费）
  DIRTY_CLEANUP_QUEUE_KEY=...           队列键（默认 badcase:dirty_cleanup:queue）
  DIRTY_CLEANUP_MAX_PENDING=800         单项目最多登记条目（超出丢弃最旧）
"""
from __future__ import annotations

import json
import os
import threading
import time
from typing import Any, Dict, List, Optional

DEFAULT_QUEUE_KEY = "badcase:dirty_cleanup:queue"
DEFAULT_MAX_PENDING = 800
MSG_TYPE = "unplanned_dirty_cleanup"
VALID_ENTITY_TYPES = ("bug", "badcase", "testcase", "card")
_MAX_ATTEMPTS = 3

_lock = threading.Lock()
_pending: Dict[int, Dict[str, Dict[str, Any]]] = {}  # project_id -> {"entity:id": item}
_worker_started = False


def cleanup_enabled() -> bool:
    """总开关：默认开；DIRTY_CLEANUP_ENABLED=0 时既不登记也不消费。"""
    return (os.getenv("DIRTY_CLEANUP_ENABLED", "1") or "1").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def queue_key() -> str:
    return (os.getenv("DIRTY_CLEANUP_QUEUE_KEY") or "").strip() or DEFAULT_QUEUE_KEY


def _max_pending() -> int:
    try:
        n = int(os.getenv("DIRTY_CLEANUP_MAX_PENDING", str(DEFAULT_MAX_PENDING)) or DEFAULT_MAX_PENDING)
    except (TypeError, ValueError):
        n = DEFAULT_MAX_PENDING
    return max(10, min(n, 10000))


def _now_ts() -> float:
    return time.time()


def _norm_project_id(project_id: Any) -> Optional[int]:
    try:
        pid = int(project_id)
    except (TypeError, ValueError):
        return None
    return pid if pid > 0 else None


def record_unplanned_dirty(
    project_id: Any,
    entity_type: str,
    record_id: Any,
    title: str = "",
) -> None:
    """grep 过滤未计划记录时登记（同 entity:id 去重；超限丢弃最旧）。"""
    if not cleanup_enabled():
        return
    pid = _norm_project_id(project_id)
    et = (entity_type or "").strip().lower()
    if pid is None or et not in VALID_ENTITY_TYPES:
        return
    try:
        rid = int(record_id)
    except (TypeError, ValueError):
        return
    if rid <= 0:
        return
    item = {
        "entity_type": et,
        "record_id": rid,
        "title": (title or "")[:200],
        "ts": _now_ts(),
    }
    key = f"{et}:{rid}"
    with _lock:
        bucket = _pending.setdefault(pid, {})
        bucket[key] = item
        cap = _max_pending()
        if len(bucket) > cap:
            oldest = sorted(bucket.items(), key=lambda kv: float(kv[1].get("ts") or 0))
            for k, _v in oldest[: len(bucket) - cap]:
                bucket.pop(k, None)


def pop_unplanned_dirty(project_id: Any) -> List[Dict[str, Any]]:
    """任务完成时取出该项目的全部登记项并清空。"""
    pid = _norm_project_id(project_id)
    if pid is None:
        return []
    with _lock:
        bucket = _pending.pop(pid, None)
    return list(bucket.values()) if bucket else []


def _restore_pending(project_id: int, items: List[Dict[str, Any]]) -> None:
    """入队失败时把条目放回登记表，等下一次任务完成重试。"""
    if not items:
        return
    with _lock:
        bucket = _pending.setdefault(int(project_id), {})
        for it in items:
            if not isinstance(it, dict):
                continue
            et = str(it.get("entity_type") or "").strip().lower()
            try:
                rid = int(it.get("record_id") or 0)
            except (TypeError, ValueError):
                continue
            if et not in VALID_ENTITY_TYPES or rid <= 0:
                continue
            bucket.setdefault(f"{et}:{rid}", it)


def enqueue_payload(payload: Dict[str, Any]) -> bool:
    """把一条清理消息 RPUSH 进 Redis 队列（同步；调用方可放线程里跑）。"""
    if not cleanup_enabled():
        return False
    try:
        from app import get_redis_client

        r = get_redis_client()
        if r is None:
            print("[DIRTY-CLEANUP] Redis 不可用，入队失败", flush=True)
            return False
        r.rpush(queue_key(), json.dumps(payload, ensure_ascii=False))
        return True
    except Exception as e:
        print(f"[DIRTY-CLEANUP] 入队异常: {e}", flush=True)
        return False


def _brief(items: List[Dict[str, Any]], limit: int = 5) -> str:
    parts = [f"{i.get('entity_type')}:{i.get('record_id')}" for i in items[:limit]]
    more = "" if len(items) <= limit else f" …(+{len(items) - limit})"
    return ", ".join(parts) + more


def flush_unplanned_to_queue(
    project_id: Any,
    *,
    session_id: str = "",
    operator_id: Any = None,
    async_send: bool = True,
) -> int:
    """总任务完成时调用：登记项打包入队（默认异步 daemon 线程发送，不阻塞收尾）。

    返回入队条目数；0 表示本次任务没有检索到未计划脏数据。
    """
    items = pop_unplanned_dirty(project_id)
    if not items:
        return 0
    pid = _norm_project_id(project_id) or 0
    payload = {
        "type": MSG_TYPE,
        "v": 1,
        "project_id": pid,
        "session_id": str(session_id or ""),
        "operator_id": operator_id,
        "ts": _now_ts(),
        "attempt": 0,
        "items": items,
    }

    def _send() -> None:
        ok = enqueue_payload(payload)
        if ok:
            print(
                f"[DIRTY-CLEANUP] 任务完成，已入队 n={len(items)} project={pid} "
                f"queue={queue_key()} sample=[{_brief(items)}]",
                flush=True,
            )
        else:
            _restore_pending(pid, items)
            print(
                f"[DIRTY-CLEANUP] 入队失败，{len(items)} 条已放回登记表待下次重试 project={pid}",
                flush=True,
            )

    if async_send:
        threading.Thread(target=_send, name="dirty-cleanup-enqueue", daemon=True).start()
    else:
        _send()
    return len(items)


# ==================== 消费者：Redis 队列 → 物理删除 ====================


def run_cleanup_worker(app, stop_event: Optional[threading.Event] = None) -> None:
    """阻塞式消费循环（BRPOP）；调用方负责放到 daemon 线程里跑。"""
    global _worker_started
    with _lock:
        if _worker_started:
            print("[DIRTY-CLEANUP] worker 已在运行，跳过重复启动", flush=True)
            return
        _worker_started = True
    if not cleanup_enabled():
        with _lock:
            _worker_started = False
        print("[DIRTY-CLEANUP] 已禁用（DIRTY_CLEANUP_ENABLED=0），worker 不启动", flush=True)
        return
    qk = queue_key()
    # BRPOP 阻塞时长必须小于 socket_timeout（get_redis_client 为 5s），
    # 否则每轮空轮询都会抛 "Timeout reading from socket" 并伴随 5s 额外延迟。
    brpop_timeout_s = 4
    print(f"[DIRTY-CLEANUP] worker 启动，BRPOP 消费队列 {qk}", flush=True)
    while not (stop_event and stop_event.is_set()):
        try:
            from app import get_redis_client

            r = get_redis_client()
            if r is None:
                time.sleep(10)
                continue
            got = r.brpop(qk, timeout=brpop_timeout_s)
            if not got:
                continue
            raw = got[1] if isinstance(got, (list, tuple)) and len(got) >= 2 else None
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8", errors="replace")
            _handle_message(app, raw)
        except Exception as e:
            print(f"[DIRTY-CLEANUP] worker 循环异常: {e}", flush=True)
            time.sleep(5)
    with _lock:
        _worker_started = False


def _handle_message(app, raw_body: Optional[str]) -> None:
    if not raw_body:
        return
    try:
        msg = json.loads(raw_body)
    except Exception as e:
        print(f"[DIRTY-CLEANUP] 消息解析失败（丢弃）: {e}", flush=True)
        return
    if not isinstance(msg, dict) or msg.get("type") != MSG_TYPE:
        return
    attempt = int(msg.get("attempt") or 0)
    try:
        stats = _process_items(app, msg)
        print(
            f"[DIRTY-CLEANUP] 消息处理完成 project={msg.get('project_id')} "
            f"n={len(msg.get('items') or [])} stats={stats}",
            flush=True,
        )
    except Exception as e:
        if attempt + 1 < _MAX_ATTEMPTS:
            msg["attempt"] = attempt + 1
            enqueue_payload(msg)
            print(
                f"[DIRTY-CLEANUP] 消息处理失败将重试 attempt={attempt + 1}: {e}",
                flush=True,
            )
        else:
            print(
                f"[DIRTY-CLEANUP] 消息处理失败且重试耗尽（丢弃）attempt={attempt}: {e}",
                flush=True,
            )


def _process_items(app, msg: Dict[str, Any]) -> Dict[str, int]:
    project_id = msg.get("project_id")
    items = msg.get("items") or []
    stats: Dict[str, int] = {}
    with app.app_context():
        for it in items:
            if not isinstance(it, dict):
                continue
            et = str(it.get("entity_type") or "").strip().lower()
            rid = it.get("record_id")
            title = str(it.get("title") or "")
            res = _delete_one(project_id, et, rid)
            key = "error" if res.startswith("error") else res
            stats[key] = stats.get(key, 0) + 1
            if res == "deleted":
                print(
                    f"[DIRTY-CLEANUP] ✅ 已删除未计划脏数据 {et}:{rid} title={title!r} project={project_id}",
                    flush=True,
                )
            else:
                print(
                    f"[DIRTY-CLEANUP] 跳过 {et}:{rid} reason={res} title={title!r}",
                    flush=True,
                )
    return stats


def _delete_one(project_id: Any, entity_type: str, record_id: Any) -> str:
    """删除单条未计划记录；返回 deleted / skip_missing / skip_planned / skip_project / error: xxx。"""
    from app import BadCase, Bug, Card, CardPlanRelation, Comment, TestCase, TestCaseComment, BugComment, db

    pid = _norm_project_id(project_id)
    et = (entity_type or "").strip().lower()
    try:
        rid = int(record_id)
    except (TypeError, ValueError):
        return "skip_unknown"
    if pid is None or et not in VALID_ENTITY_TYPES or rid <= 0:
        return "skip_unknown"
    try:
        if et == "bug":
            row = db.session.get(Bug, rid)
            if row is None:
                return "skip_missing"
            if int(getattr(row, "project_id", 0) or 0) != pid:
                return "skip_project"
            if getattr(row, "plan_id", None) not in (None, "", 0):
                return "skip_planned"
            BugComment.query.filter(BugComment.bug_id == rid).delete(synchronize_session=False)
            for cid in _orphan_card_ids_for_source(et, rid, getattr(row, "card_id", None)):
                _delete_card_row(cid)
            db.session.delete(row)
            db.session.commit()
        elif et == "badcase":
            row = db.session.get(BadCase, rid)
            if row is None:
                return "skip_missing"
            if int(getattr(row, "project_id", 0) or 0) != pid:
                return "skip_project"
            if getattr(row, "plan_id", None) not in (None, "", 0):
                return "skip_planned"
            Comment.query.filter(Comment.badcase_id == rid).delete(synchronize_session=False)
            for cid in _orphan_card_ids_for_source(et, rid, getattr(row, "card_id", None)):
                _delete_card_row(cid)
            db.session.delete(row)
            db.session.commit()
        elif et == "testcase":
            row = db.session.get(TestCase, rid)
            if row is None:
                return "skip_missing"
            if int(getattr(row, "project_id", 0) or 0) != pid:
                return "skip_project"
            if getattr(row, "plan_id", None) not in (None, "", 0):
                return "skip_planned"
            TestCaseComment.query.filter(TestCaseComment.test_case_id == rid).delete(synchronize_session=False)
            for cid in _orphan_card_ids_for_source(et, rid, getattr(row, "card_id", None)):
                _delete_card_row(cid)
            db.session.delete(row)
            db.session.commit()
        else:  # card
            row = db.session.get(Card, rid)
            if row is None:
                return "skip_missing"
            if int(getattr(row, "project_id", 0) or 0) != pid:
                return "skip_project"
            if getattr(row, "plan_id", None) not in (None, "", 0):
                return "skip_planned"
            CardPlanRelation.query.filter(CardPlanRelation.card_id == rid).delete(synchronize_session=False)
            db.session.delete(row)
            db.session.commit()
    except Exception as e:
        try:
            db.session.rollback()
        except Exception:
            pass
        return f"error: {e}"
    _after_delete(pid, et, rid)
    return "deleted"


_SOURCE_TYPE_ALIASES: Dict[str, tuple] = {
    "bug": ("bug", "BUG"),
    "badcase": ("bad_case", "badcase", "BADCASE"),
    "testcase": ("test_case", "testcase", "TESTCASE"),
}


def _orphan_card_ids_for_source(entity_type: str, record_id: int, card_id: Any) -> List[int]:
    """找出与源记录绑定的卡片中「没有其他记录引用」的 id（可安全连带删除）。"""
    from app import Card

    candidates: List[int] = []

    def _add(v: Any) -> None:
        try:
            iv = int(v)
        except (TypeError, ValueError):
            return
        if iv > 0 and iv not in candidates:
            candidates.append(iv)

    _add(card_id)
    aliases = _SOURCE_TYPE_ALIASES.get(entity_type) or ()
    try:
        q = Card.query.filter(Card.source_id == int(record_id))
        if aliases:
            q = q.filter(Card.source_type.in_(aliases))
        for row in q.all():
            _add(getattr(row, "id", None))
    except Exception as e:
        print(f"[DIRTY-CLEANUP] 查询关联卡片失败 {entity_type}:{record_id}: {e}", flush=True)
    out: List[int] = []
    for cid in candidates:
        if _card_in_use_by_others(cid, exclude_entity_type=entity_type, exclude_record_id=record_id):
            print(f"[DIRTY-CLEANUP] 跳过删 Card id={cid}（仍被其他记录引用）", flush=True)
            continue
        out.append(cid)
    return out


def _card_in_use_by_others(
    card_id: int,
    *,
    exclude_entity_type: Optional[str] = None,
    exclude_record_id: Optional[int] = None,
) -> bool:
    """Bug/BadCase/TestCase 任一行仍引用该 card_id 时返回 True。"""
    from app import BadCase, Bug, TestCase

    checks = (
        ("bug", Bug, Bug.card_id),
        ("badcase", BadCase, BadCase.card_id),
        ("testcase", TestCase, TestCase.card_id),
    )
    for et, model, col in checks:
        q = model.query.filter(col == card_id)
        if et == exclude_entity_type and exclude_record_id is not None:
            q = q.filter(model.id != int(exclude_record_id))
        if q.first() is not None:
            return True
    return False


def _delete_card_row(card_id: int) -> None:
    """删除卡片及其计划关系（不 commit，由调用方统一提交）。"""
    from app import Card, CardPlanRelation, db

    CardPlanRelation.query.filter(CardPlanRelation.card_id == card_id).delete(synchronize_session=False)
    row = db.session.get(Card, card_id)
    if row is not None:
        db.session.delete(row)
        print(f"[DIRTY-CLEANUP] 连带删除孤儿 Card id={card_id}", flush=True)


def _after_delete(project_id: int, entity_type: str, record_id: int) -> None:
    """行删除提交完成后：删 ES 索引 + 失效项目缓存（与正式删除 API 对齐）。"""
    try:
        from app import _schedule_grep_work_item_delete

        _schedule_grep_work_item_delete(entity_type, record_id)
    except Exception as e:
        print(f"[DIRTY-CLEANUP] ES 索引删除跳过 {entity_type}:{record_id}: {e}", flush=True)
    try:
        from app import _redis_cache_invalidate_project

        _redis_cache_invalidate_project(project_id)
    except Exception as e:
        print(f"[DIRTY-CLEANUP] 缓存失效跳过 project={project_id}: {e}", flush=True)
