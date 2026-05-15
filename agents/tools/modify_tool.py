"""
对话修改Bug/BadCase工具
支持行级别对比显示修改内容，集成Text2SQL智能查询
"""
from typing import Any, Dict, FrozenSet, List, Optional, Tuple, Union
from agents.tool_registry import BaseTool
from agents.locale_prompts import (
    normalize_locale,
    is_english_locale,
    modify_tool_progress,
    modify_text2sql_row_question,
    modify_error_target_id_bad,
    modify_error_missing_params,
    modify_error_immutable_fields,
    modify_error_row_not_found,
    modify_message_sandbox_done,
    modify_summary_preview,
    modify_message_apply_ok,
    modify_message_apply_fail,
    modify_summary_applied,
    modify_error_apply_exception,
    modify_modifications_kv_summary,
    modify_message_readonly_no_modifications,
    modify_summary_readonly_snapshot,
    modify_error_batch_requires_modifications,
    modify_assignee_unassigned,
    modify_modifiable_fields_rows,
    modify_field_label,
    react_batch_modify_preview_message,
    react_batch_modify_summary,
)
from config import Config
import difflib
import json
import os
import sqlite3
from concurrent.futures import ThreadPoolExecutor
import tempfile
import time
import uuid

# Text2SQL Agent
try:
    from .sqlcoder_agent import LLMBackend, get_cached_text2sql_agent
    TEXT2SQL_AVAILABLE = True
except ImportError:
    TEXT2SQL_AVAILABLE = False

# 批量预览流式事件：经 progress_queue 透传到 SSE（前缀 + JSON）
MODIFY_BATCH_ROW_PREFIX = "__MODIFY_BATCH_ROW__"


def _json_safe_id(value: Any) -> Any:
    """前端 JSON.parse 会丢大整数精度：对外 payload 中主键一律用十进制字符串。"""
    if value is None:
        return None
    try:
        return str(int(value))
    except (TypeError, ValueError):
        return value


def _json_safe_row(snapshot: Any) -> Any:
    """before/after 快照中的整型主键/外键转为字符串再 JSON 下发。"""
    if not isinstance(snapshot, dict):
        return snapshot
    out = dict(snapshot)
    for k in (
        "id",
        "plan_id",
        "card_id",
        "source_id",
        "assignee_id",
        "parent_id",
        "bug_id",
        "badcase_id",
        "testcase_id",
        "navigation_plan_id",
        "copy_from_card_id",
        "created_id",
    ):
        if k in out and out[k] is not None:
            out[k] = _json_safe_id(out[k])
    return out


def modify_tool_params_log_snapshot(
    params: Optional[Dict[str, Any]],
    *,
    ctx_grep_ids: Any = None,
) -> Dict[str, Any]:
    """供主循环 / spawn_executor 打印入参：剔除不可序列化项，长串截断。"""
    if not isinstance(params, dict):
        return {}
    out: Dict[str, Any] = {}
    for k, v in params.items():
        if k in ("progress_queue", "progress_callback"):
            continue
        if k == "natural_query" and isinstance(v, str) and len(v) > 200:
            out[k] = v[:200] + "…"
            continue
        if k == "modifications" and isinstance(v, dict):
            out[k] = {
                str(ik): (str(iv)[:240] if not isinstance(iv, (dict, list)) else type(iv).__name__)
                for ik, iv in list(v.items())[:24]
            }
            continue
        if isinstance(v, (str, int, float, bool)) or v is None:
            out[k] = v
        elif isinstance(v, dict):
            out[k] = f"<dict n={len(v)}>"
        elif isinstance(v, (list, tuple)):
            out[k] = f"<list n={len(v)}>"
        else:
            out[k] = type(v).__name__
    if ctx_grep_ids is not None:
        out["_ctx_grep_ids"] = ctx_grep_ids
    return out


class ModifyTool(BaseTool):
    """对话修改 Bug / BadCase / TestCase / 统一卡片(Card) 的工具"""
    
    def __init__(self, db_session, database_uri: str = None):
        self.db = db_session
        self.name = "modify"
        self.description = """
用于修改 Bug / BadCase / 测试用例(testcase) / **统一迭代卡片(Card)** / **迭代计划(Plan)** 的工具，支持对话式修改和行级别对比。

**如何选择 target（必须遵守，优先级高于「grep 是否命中 card」）：**
1) **先看 modifications 里的字段属于哪张源表**：缺陷工作流字段（如 status、steps_to_reproduce、severity、expected_result、actual_result 等）**一律**用 **target='bug'** 且 **target_id=Bug 源表主键**；BadCase/测例专用字段同理用 badcase/testcase。**禁止**用 target='card' 去改 Bug 状态或复现步骤（Card 行上通常没有这些列，会导致错误 SQL）。
2) **grep 使用 target=card** 只表示「在 Card 表里检索/定位」，**不表示**下一步 modify 也要 target=card。定位到迭代行后若要改缺陷状态等，modify 仍须 **target=bug**（或从 observation 的 bug_list / 合并导航里的源表 id 取 target_id）；需要关联卡片时可选传 **card_id**，由服务端按 Card.source_type 校正。
3) **仅当**用户明确要改「**卡片层**」展示信息（且语义是改 Card 行上的 title/description 等），或 modifications **仅含** Card 表自身可写、且无意图写源表独有字段时，才用 **target='card'** + **card_id**（或 target_id=card.id）。
4) 勿仅凭列表在 UI 上像「一行卡片」就把 modify 设为 card；也勿仅凭标题里出现 bug/testcase 字样推断类型——以 **字段归属** 与 grep 结果中的 **source_type / bug_list** 为准。

使用场景示例：
- 改状态 / 复现 / 严重程度 → target=bug（或 badcase/testcase），target_id 为对应源表 id
- 「修改卡片的标题/描述…」且明确指 Card 展示层 → target=card，modifications 含 title/description
- 「修改这个 Bug 的标题」→ target=bug（或 grep target=bug 取 Bug.id）

参数：
- target: 'bug' | 'badcase' | 'testcase' | 'card' | 'plan'（plan 时为迭代计划表 Plan.id）
- target_id: 当前 target 对应表的主键（**target=card 时为 card.id**；**target=plan 时为 plan.id**；其余为源表 id）
- card_id: Card 表主键（可选，用于与源行关联或辅助定位；**改 Bug 字段时仍可传 card_id，但 target 须为 bug**）
- modifications: {"字段名": "新值"}
- project_id: 项目ID（必需）
- natural_query: 自然语言查询（可选）

返回：before / after / diff / confirmation_required 等。
"""
        
        # 延迟初始化 Text2SQL（采纳时不需要，仅沙箱预览 / natural_query 时再初始化）
        self._database_uri = database_uri
        self.text2sql = None

    def _canonical_target_from_card_source_type(self, source_type: Optional[str]) -> Optional[str]:
        """Card.source_type → modify 的 target（权威）；避免模型根据标题里「testcase」等字样误选。"""
        if not source_type:
            return None
        st = str(source_type).strip().lower()
        if st in ("bug",):
            return "bug"
        if st in ("badcase", "bad_case"):
            return "badcase"
        if st in ("testcase", "test_case"):
            return "testcase"
        return None

    def _disambiguate_numeric_id_as_card_id(
        self, raw_id: Any, project_id: Any
    ) -> Optional[int]:
        """
        模型常把「卡片主键」误填到 target_id。若该数字在本项目中存在对应 Card 行，则视为 card_id。
        """
        try:
            cid = int(raw_id)
            pid = int(project_id)
        except Exception:
            return None
        try:
            from app import app as flask_app, db as flask_db, Card

            with flask_app.app_context():
                row = (
                    flask_db.session.query(Card)
                    .filter(Card.id == cid, Card.project_id == pid)
                    .first()
                )
                return cid if row is not None else None
        except Exception:
            return None

    def _modify_source_row_exists(
        self, target: str, target_id: Any, project_id: Any
    ) -> bool:
        """声明为 bug/badcase/testcase 时，若该主键在本项目源表中确有行，则不得因与 Card.id 撞号改写为 card。"""
        tl = (str(target or "")).strip().lower()
        if tl not in ("bug", "badcase", "testcase"):
            return False
        try:
            tid = int(target_id)
            pid = int(project_id)
        except (TypeError, ValueError):
            return False
        try:
            from app import app as flask_app, db as flask_db, Bug, BadCase, TestCase

            with flask_app.app_context():
                if tl == "bug":
                    return (
                        flask_db.session.query(Bug)
                        .filter(Bug.id == tid, Bug.project_id == pid)
                        .first()
                        is not None
                    )
                if tl == "badcase":
                    return (
                        flask_db.session.query(BadCase)
                        .filter(BadCase.id == tid, BadCase.project_id == pid)
                        .first()
                        is not None
                    )
                return (
                    flask_db.session.query(TestCase)
                    .filter(TestCase.id == tid, TestCase.project_id == pid)
                    .first()
                    is not None
                )
        except Exception:
            return False

    def _normalize_target_using_card_row(
        self, target: str, project_id: Any, card_id: Any
    ) -> Tuple[str, bool]:
        """
        若 params 含 card_id，则以 Card 表中 source_type 为准覆盖 target。
        返回 (校正后的 target, 是否发生过校正)。
        """
        try:
            pid = int(project_id)
            cid = int(card_id)
        except Exception:
            return target, False
        try:
            from app import app as flask_app, db as flask_db, Card

            with flask_app.app_context():
                card = (
                    flask_db.session.query(Card)
                    .filter(Card.id == cid, Card.project_id == pid)
                    .first()
                )
                if card is None:
                    return target, False
                canon = self._canonical_target_from_card_source_type(
                    getattr(card, "source_type", None)
                )
                if not canon:
                    return target, False
                cur = (target or "bug").strip().lower()
                if canon != cur:
                    print(
                        f"[MODIFY] card_id={cid} 按 Card.source_type 校正 target: {cur!r} → {canon!r}",
                        flush=True,
                    )
                    return canon, True
                return canon, False
        except Exception:
            return target, False

    def _infer_modify_target_from_modification_keys(self, modifications: Dict[str, Any]) -> Optional[str]:
        """当同一 project 下 bug/badcase/testcase 主键撞号时，用修改字段粗判真实类型（仅作歧义消解）。"""
        if not modifications or not isinstance(modifications, dict):
            return None
        keys = {str(k).strip().lower() for k in modifications.keys()}
        bugish = {
            "status",
            "状态",
            "steps_to_reproduce",
            "expected_result",
            "actual_result",
            "severity",
            "description",
            "assignee",
            "assignee_id",
        }
        badish = {
            "reproduction_steps",
            "answer",
            "correct_answer",
            "badcase_result",
            "base_problem",
            "case_category",
        }
        tcish = {"preconditions", "steps", "remark", "baseline", "test_type", "case_type"}
        b_hit = bool(keys & bugish)
        d_hit = bool(keys & badish)
        t_hit = bool(keys & tcish)
        if b_hit and not d_hit and not t_hit:
            return "bug"
        if d_hit and not b_hit and not t_hit:
            return "badcase"
        if t_hit and not b_hit and not d_hit:
            return "testcase"
        return None

    def _reconcile_modify_target_from_db(
        self,
        target: Optional[str],
        target_id: int,
        project_id: int,
        modifications: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        模型常把 target 写成 badcase，实际要改的是 Bug 源行（或反之）。
        在已解析出 project_id + 源表主键 target_id 后：
        1) 优先用 Card.source_id + source_type 作为权威；
        2) 无 Card 时若仅一张源表存在该 id，则采用该表类型；
        3) 多张表同 id 时尝试用 modifications 字段集消歧。
        """
        tl = (str(target or "bug")).strip().lower()
        if tl in ("card", "plan"):
            return tl
        try:
            pid = int(project_id)
            tid = int(target_id)
        except (TypeError, ValueError):
            return tl
        try:
            from app import app as flask_app

            def _enumish(v: Any) -> Optional[str]:
                if v is None:
                    return None
                if hasattr(v, "value"):
                    return str(getattr(v, "value"))
                s = str(v).strip()
                return s if s else None

            def _card_rows_snapshot() -> List[Dict[str, Any]]:
                with flask_app.app_context():
                    from app import db as _db, Card as _Card

                    try:
                        rows = (
                            _db.session.query(_Card)
                            .filter(_Card.project_id == pid, _Card.source_id == tid)
                            .all()
                        )
                        return [
                            {
                                "id": int(r.id),
                                "source_type": _enumish(getattr(r, "source_type", None)),
                                "type": _enumish(getattr(r, "type", None)),
                            }
                            for r in rows
                        ]
                    finally:
                        try:
                            _db.session.remove()
                        except Exception:
                            pass

            def _has_bug_row() -> bool:
                with flask_app.app_context():
                    from app import db as _db, Bug as _B

                    try:
                        return (
                            _db.session.query(_B.id)
                            .filter(_B.project_id == pid, _B.id == tid)
                            .first()
                            is not None
                        )
                    finally:
                        try:
                            _db.session.remove()
                        except Exception:
                            pass

            def _has_badcase_row() -> bool:
                with flask_app.app_context():
                    from app import db as _db, BadCase as _Bc

                    try:
                        return (
                            _db.session.query(_Bc.id)
                            .filter(_Bc.project_id == pid, _Bc.id == tid)
                            .first()
                            is not None
                        )
                    finally:
                        try:
                            _db.session.remove()
                        except Exception:
                            pass

            def _has_testcase_row() -> bool:
                with flask_app.app_context():
                    from app import db as _db, TestCase as _Tc

                    try:
                        return (
                            _db.session.query(_Tc.id)
                            .filter(_Tc.project_id == pid, _Tc.id == tid)
                            .first()
                            is not None
                        )
                    finally:
                        try:
                            _db.session.remove()
                        except Exception:
                            pass

            def _safe_result(name: str, fut, default):
                try:
                    return fut.result(timeout=45)
                except Exception as e:
                    print(f"[MODIFY] reconcile 并发任务 {name} 失败，回退默认值: {e}", flush=True)
                    return default

            with ThreadPoolExecutor(max_workers=4) as ex:
                f_card = ex.submit(_card_rows_snapshot)
                f_bug = ex.submit(_has_bug_row)
                f_bad = ex.submit(_has_badcase_row)
                f_tc = ex.submit(_has_testcase_row)
                cards_payload = _safe_result("cards", f_card, [])
                has_bug = bool(_safe_result("bug", f_bug, False))
                has_bad = bool(_safe_result("badcase", f_bad, False))
                has_tc = bool(_safe_result("testcase", f_tc, False))

            if len(cards_payload) == 1:
                c0 = cards_payload[0]
                canon = self._canonical_target_from_card_source_type(c0.get("source_type"))
                if not canon:
                    ct_s = str(c0.get("type") or "").strip().lower()
                    canon = self._canonical_target_from_card_source_type(ct_s)
                if canon and canon != tl:
                    print(
                        f"[MODIFY] 按 Card.source_type/type 校正 target: {tl!r} → {canon!r} "
                        f"(card.id={c0.get('id')}, source_id={tid})",
                        flush=True,
                    )
                    return canon
            if len(cards_payload) > 1:
                print(
                    f"[MODIFY] WARN 多条 Card 共用 source_id={tid}（n={len(cards_payload)}），"
                    f"尝试源表消歧当前 target={tl!r}",
                    flush=True,
                )

            hits: List[str] = []
            if has_bug:
                hits.append("bug")
            if has_bad:
                hits.append("badcase")
            if has_tc:
                hits.append("testcase")
            if len(hits) == 1 and hits[0] != tl:
                print(
                    f"[MODIFY] 按源表唯一命中校正 target: {tl!r} → {hits[0]!r} (id={tid})",
                    flush=True,
                )
                return hits[0]
            if len(hits) > 1:
                hinted = self._infer_modify_target_from_modification_keys(modifications or {})
                if hinted and hinted in hits and hinted != tl:
                    print(
                        f"[MODIFY] 按 modifications 字段校正 target: {tl!r} → {hinted!r} (id={tid})",
                        flush=True,
                    )
                    return hinted
        except Exception as e:
            print(f"[MODIFY] target 校正查询异常，沿用 {tl!r}: {e}", flush=True)
        return tl

    def _resolve_target_id_from_card_id(self, target: str, card_id: Any, project_id: Any) -> Optional[int]:
        """
        卡片层适配：优先用 card_id 在 Card 表中定位 source_type/source_id；
        若 Card 未关联源表，再回退到源表的 card_id 字段（仅部分表存在）。
        """
        try:
            if card_id is None or project_id is None:
                return None
            cid = int(card_id)
            pid = int(project_id)
        except Exception:
            return None
        try:
            from app import app as flask_app, db as flask_db
            with flask_app.app_context():
                # 1) 优先查 Card 表（卡片层权威映射）
                try:
                    from app import Card
                    card = (
                        flask_db.session.query(Card)
                        .filter(Card.id == cid, Card.project_id == pid)
                        .first()
                    )
                    if card is not None:
                        tl = (target or "").strip().lower()
                        sid = getattr(card, "source_id", None)
                        # target=card：无 source 映射时不要落到 Bug.card_id，否则会绑错多条缺陷
                        if tl == "card":
                            if sid is not None and str(sid).strip():
                                try:
                                    return int(sid)
                                except Exception:
                                    return None
                            return None
                        if sid is not None and str(sid).strip():
                            canon_st = self._canonical_target_from_card_source_type(
                                getattr(card, "source_type", None)
                            )
                            if canon_st and tl not in ("card",):
                                if canon_st != tl:
                                    return None
                            try:
                                return int(sid)
                            except Exception:
                                return None
                except Exception:
                    # ignore，回退源表查找
                    pass

                # 2) 回退：源表存在 card_id 列时可直接反查
                from app import Bug, BadCase, TestCase
                if target == "bug":
                    row = (
                        flask_db.session.query(Bug)
                        .filter(Bug.project_id == pid, Bug.card_id == cid)
                        .first()
                    )
                elif target == "badcase":
                    row = (
                        flask_db.session.query(BadCase)
                        .filter(BadCase.project_id == pid, BadCase.card_id == cid)
                        .first()
                    )
                elif target == "testcase":
                    row = (
                        flask_db.session.query(TestCase)
                        .filter(TestCase.project_id == pid, TestCase.card_id == cid)
                        .first()
                    )
                else:
                    return None
                if row is None:
                    return None
                return int(getattr(row, "id"))
        except Exception:
            return None

    def _nav_card_pk_for_source_orm_row(
        self, session: Any, target: str, row: Any, project_id: Any
    ) -> Optional[int]:
        """列表跳转用：Bug/BadCase/TestCase 行关联的 Card.id（优先行上 card_id，否则按 source 反查）。"""
        card = self._find_card_for_source_row(session, target, row, project_id)
        if card is None:
            return None
        try:
            return int(getattr(card, "id", None))
        except (TypeError, ValueError):
            return None

    def _card_sync_from_source_enabled(self) -> bool:
        """modify 写入源表后是否镜像更新 Card；默认开启，MODIFY_SYNC_CARD_FROM_SOURCE=0 关闭。"""
        return self._env_flag_enabled("MODIFY_SYNC_CARD_FROM_SOURCE", "1")

    def _find_card_for_source_row(
        self, session: Any, target: str, row: Any, project_id: int
    ) -> Optional[Any]:
        """用 bug.card_id / testcase.card_id（若有）或 Card.source_type+source_id 定位卡片。"""
        if row is None:
            return None
        try:
            from app import Card, CardType

            pid = int(project_id)
            cid = getattr(row, "card_id", None)
            if cid is not None:
                try:
                    ci = int(cid)
                except (TypeError, ValueError):
                    ci = None
                if ci is not None and ci > 0:
                    card = (
                        session.query(Card)
                        .filter(Card.id == ci, Card.project_id == pid)
                        .first()
                    )
                    if card is not None:
                        return card
            rid = int(getattr(row, "id"))
            aliases = {
                "bug": ["bug"],
                "badcase": ["badcase", "bad_case"],
                "testcase": ["testcase", "test_case"],
            }
            norm_set = {a.replace("-", "_").lower() for a in aliases.get(target, [])}
            expected_ct = {
                "bug": CardType.BUG,
                "badcase": CardType.BADCASE,
                "testcase": CardType.TESTCASE,
            }.get(target)

            candidates = (
                session.query(Card)
                .filter(Card.project_id == pid, Card.source_id == rid)
                .all()
            )
            for c in candidates:
                st = str(getattr(c, "source_type", None) or "").strip().lower().replace("-", "_")
                if st in norm_set:
                    return c
            if expected_ct is not None:
                for c in candidates:
                    if getattr(c, "type", None) == expected_ct:
                        return c
            if len(candidates) == 1:
                return candidates[0]
            return None
        except Exception as e:
            print(f"[MODIFY] 查找 Card 失败: {e}")
            return None

    def _sync_card_from_source_row(
        self, session: Any, target: str, row: Any, project_id: int
    ) -> None:
        """将 Bug/BadCase/TestCase 当前行镜像到关联 Card（须在源表字段已更新后、同一 commit 前调用）。

        注意：**不同步源表 title → Card.title**。迭代左侧「卡片」标题由 Card 独立维护；
        修改 Bug/用例/BadCase 的标题只写源表，不应改写外层卡片标题。
        """
        if not self._card_sync_from_source_enabled():
            return
        try:
            from app import CardType

            card = self._find_card_for_source_row(session, target, row, project_id)
            if card is None:
                return
            expected = {
                "bug": CardType.BUG,
                "badcase": CardType.BADCASE,
                "testcase": CardType.TESTCASE,
            }.get(target)
            if expected is not None:
                ct = getattr(card, "type", None)
                cv = getattr(ct, "value", ct)
                ev = getattr(expected, "value", expected)
                if cv != ev:
                    print(
                        f"[MODIFY] Card id={card.id} 类型与源表 {target} 不一致，跳过镜像"
                    )
                    return

            if target == "bug":
                card.plan_id = getattr(row, "plan_id", None)
                card.priority = getattr(row, "priority", None) or card.priority
                card.assignee_id = getattr(row, "assignee_id", None)
                card.description = getattr(row, "description", None)
                card.severity = getattr(row, "severity", None)
                card.steps_to_reproduce = getattr(row, "steps_to_reproduce", None)
                card.expected_result = getattr(row, "expected_result", None)
                card.actual_result = getattr(row, "actual_result", None)
                card.bug_type = getattr(row, "bug_type", None)
                card.environment = getattr(row, "environment", None)
                card.browser = getattr(row, "browser", None)
                card.os = getattr(row, "os", None)
            elif target == "badcase":
                card.plan_id = getattr(row, "plan_id", None)
                card.priority = getattr(row, "priority", None) or card.priority
                card.description = getattr(row, "base_problem", None)
                card.case_category = getattr(row, "case_category", None)
                card.base_problem = getattr(row, "base_problem", None)
                card.reproduction_steps = getattr(row, "reproduction_steps", None)
                card.badcase_result = getattr(row, "badcase_result", None)
                card.answer = getattr(row, "answer", None)
                card.correct_answer = getattr(row, "correct_answer", None)
                card.problem_reason = getattr(row, "problem_reason", None)
                card.solution = getattr(row, "solution", None)
                av = getattr(row, "assignee", None)
                if av is not None and str(av).strip().isdigit():
                    try:
                        card.assignee_id = int(str(av).strip())
                    except Exception:
                        pass
            elif target == "testcase":
                card.plan_id = getattr(row, "plan_id", None)
                card.priority = getattr(row, "priority", None) or card.priority
                card.assignee_id = getattr(row, "assignee_id", None)
                card.description = getattr(row, "remark", None)
                card.case_type_test = getattr(row, "case_type", None)
                card.test_type = getattr(row, "test_type", None)
                card.preconditions = getattr(row, "preconditions", None)
                card.steps = getattr(row, "steps", None)
                card.remark = getattr(row, "remark", None)
                card.requirement_id = getattr(row, "requirement_id", None)
                card.related_defects = getattr(row, "related_defects", None)
                card.last_executed = getattr(row, "last_executed", None)
                card.executed_by = getattr(row, "executed_by", None)
                card.execution_result = getattr(row, "execution_result", None)
                card.baseline = getattr(row, "baseline", None)
                card.estimated_time = getattr(row, "estimated_time", None)
                card.actual_time = getattr(row, "actual_time", None)
                card.remaining_time = getattr(row, "remaining_time", None)
                card.version = getattr(row, "version", None) or card.version
        except Exception as e:
            print(f"[MODIFY] Card 镜像同步失败（源表写入仍保留）: {e}")

    def _resolve_linked_source_row_for_card_modify(
        self, session: Any, card: Any, project_id: int
    ) -> Tuple[Optional[str], Any]:
        """Card 表无 status 等列时，解析其关联的 Bug/BadCase/TestCase 行（与快照反查 bug.card_id 同源）。"""
        if card is None:
            return None, None
        try:
            from app import Bug, BadCase, TestCase, CardType

            pid = int(project_id)
            st_raw = (getattr(card, "source_type", None) or "").strip().lower()
            sid = getattr(card, "source_id", None)

            def _canon_st(s: str) -> Optional[str]:
                if s in ("bug", "defect"):
                    return "bug"
                if s in ("bad_case", "badcase", "bad-case"):
                    return "badcase"
                if s in ("test_case", "testcase", "test-case"):
                    return "testcase"
                return None

            ct = _canon_st(st_raw)
            if ct and sid is not None:
                try:
                    iid = int(sid)
                except (TypeError, ValueError):
                    iid = None
                if iid is not None and iid > 0:
                    if ct == "bug":
                        row = (
                            session.query(Bug)
                            .filter(Bug.id == iid, Bug.project_id == pid)
                            .first()
                        )
                        if row:
                            return "bug", row
                    elif ct == "badcase":
                        row = (
                            session.query(BadCase)
                            .filter(BadCase.id == iid, BadCase.project_id == pid)
                            .first()
                        )
                        if row:
                            return "badcase", row
                    elif ct == "testcase":
                        row = (
                            session.query(TestCase)
                            .filter(TestCase.id == iid, TestCase.project_id == pid)
                            .first()
                        )
                        if row:
                            return "testcase", row

            ctype = getattr(card, "type", None)
            cv = getattr(ctype, "value", ctype)
            cv_s = str(cv).strip().lower() if cv is not None else ""
            if cv_s == "bug" or ctype == CardType.BUG:
                row = (
                    session.query(Bug)
                    .filter(Bug.card_id == int(card.id), Bug.project_id == pid)
                    .order_by(Bug.id.asc())
                    .first()
                )
                if row:
                    return "bug", row
            if cv_s == "badcase" or ctype == CardType.BADCASE:
                row = (
                    session.query(BadCase)
                    .filter(BadCase.card_id == int(card.id), BadCase.project_id == pid)
                    .order_by(BadCase.id.asc())
                    .first()
                )
                if row:
                    return "badcase", row
            if cv_s == "testcase" or ctype == CardType.TESTCASE:
                row = (
                    session.query(TestCase)
                    .filter(TestCase.card_id == int(card.id), TestCase.project_id == pid)
                    .order_by(TestCase.id.asc())
                    .first()
                )
                if row:
                    return "testcase", row
            return None, None
        except Exception as e:
            print(f"[MODIFY] 解析 Card 关联源表行失败: {e}")
            return None, None

    def _apply_fields_to_card_and_linked_source(
        self,
        session: Any,
        card: Any,
        modifications: Dict[str, Any],
        project_id: int,
    ) -> bool:
        """先写 Card 上存在的列；其余（如 status）写到关联 Bug/BadCase/TestCase，再镜像 Card。"""
        if not card or not modifications:
            return False
        source_target, source_row = self._resolve_linked_source_row_for_card_modify(
            session, card, project_id
        )
        applied = False
        pid = int(project_id)

        for field, value in modifications.items():
            actual_field = self._map_field_name(field, "card")
            actual_value = (
                value["new"] if isinstance(value, dict) and "new" in value else value
            )

            if hasattr(card, actual_field):
                setattr(card, actual_field, actual_value)
                applied = True
                continue

            if source_row is None or not source_target:
                print(
                    f"[MODIFY] Card id={getattr(card, 'id', '?')} 字段 {field} 无法落 Card 且无关联源表行，跳过"
                )
                continue

            st_field = self._map_field_name(field, source_target)
            if not hasattr(source_row, st_field):
                print(
                    f"[MODIFY] Card id={getattr(card, 'id', '?')} 源表 {source_target} 无列 {st_field}，跳过 {field}"
                )
                continue

            if st_field == "status":
                actual_value = self._normalize_status(str(actual_value), source_target)
                if source_target == "badcase":
                    try:
                        from app import BadCaseStatus

                        actual_value = BadCaseStatus(actual_value)
                    except Exception:
                        pass
                elif source_target == "testcase":
                    try:
                        from app import TestCaseStatus

                        actual_value = TestCaseStatus(actual_value)
                    except Exception:
                        pass

            setattr(source_row, st_field, actual_value)
            applied = True
            self._sync_card_from_source_row(session, source_target, source_row, pid)

        return applied

    def _ensure_text2sql(self):
        """仅在实际需要时初始化 Text2SQL（沙箱预览 / 自然语言查询）"""
        if self.text2sql is not None:
            return
        if TEXT2SQL_AVAILABLE:
            try:
                db_path = self._database_uri or 'instance/badcase_doctor.db'
                # 默认用 glm-4-flash（更快更稳）；如需 glm-5 可通过环境变量指定
                import os
                backend_env = (os.getenv("TEXT2SQL_LLM_BACKEND", "glm-4-flash") or "").strip().lower()
                backend = LLMBackend.GLM_5.value if backend_env in ("glm-5", "glm5") else LLMBackend.GLM_4_FLASH.value
                self.text2sql = get_cached_text2sql_agent(
                    database_path=db_path,
                    llm_backend=backend,
                    debug=False,
                    execution_mode="direct",
                )
                print(f"[MODIFY] Text2SQL 延迟初始化完成")
                if os.getenv("PERF_LOG", "").strip() == "1" and self.text2sql is not None:
                    try:
                        _m = getattr(getattr(self.text2sql, "llm", None), "model_name", None)
                    except Exception:
                        _m = None
                    print(
                        f"[PERF][modify_text2sql] cache_backend={backend!r} "
                        f"llm_model_name={_m!r} "
                        f"TEXT2SQL_MODEL_env={(os.getenv('TEXT2SQL_MODEL') or '').strip()!r} "
                        f"TEXT2SQL_LLM_BACKEND_env={(os.getenv('TEXT2SQL_LLM_BACKEND') or '').strip()!r} "
                        f"TEXT2SQL_PROVIDER_env={(os.getenv('TEXT2SQL_PROVIDER') or '').strip()!r}",
                        flush=True,
                    )
            except Exception as e:
                self.text2sql = None
                print(f"[MODIFY] Text2SQL初始化失败: {e}")

    @staticmethod
    def _env_flag_enabled(name: str, default: str = "1") -> bool:
        v = (os.getenv(name, default) or default).strip().lower()
        return v not in ("0", "false", "no", "off", "")

    def _sanitize_title_modifications(
        self,
        target: str,
        modifications: Dict[str, Any],
        original_data: Optional[Dict[str, Any]],
        natural_query: Optional[str],
        *,
        batch_mode: bool = False,
    ) -> Dict[str, Any]:
        """
        模型常把用户话里的「Bug/卡片名称」误写入 modifications.title。
        写入源表后 MODIFY_SYNC_CARD_FROM_SOURCE 会镜像其它字段；**title 不再镜像到 Card**，
        但若误写仍会污染 Bug/BadCase/TestCase 的标题字段。
        规则：无明确「改标题」意图且同时改其它字段时剔除 title；或与当前行标题相同则剔除冗余。
        """
        if target not in ("bug", "badcase", "testcase", "card", "plan"):
            return modifications
        if "title" not in modifications:
            return modifications
        m = dict(modifications)
        nq = (natural_query or "").strip()
        title_intent_markers = (
            "标题改为",
            "改标题",
            "标题改成",
            "重命名",
            "改名为",
            "改成叫",
            "名称改为",
            "题目改为",
            "rename",
            "title to",
            "change title",
        )
        nq_lower = nq.lower()
        has_title_intent = any(x in nq for x in title_intent_markers) or (
            "title" in nq_lower
            and ("rename" in nq_lower or "change" in nq_lower or "改为" in nq)
        )

        old_t = ""
        if original_data:
            old_t = str(original_data.get("title") or "").strip()
        new_t = str(m.get("title") or "").strip()
        if old_t and new_t == old_t:
            m.pop("title", None)
            print("[MODIFY] 剔除冗余 title（与当前记录标题相同）", flush=True)
            return m

        # 仅有 title、且无显式「改标题」话术：防模型把 grep 到的实体名误写入 title。
        # 若新标题与旧标题不同（或尚无旧标题），说明确有文案变更，必须保留，否则 diff 为空、沙箱「0 项」。
        if (
            not batch_mode
            and set(m.keys()) == {"title"}
            and not has_title_intent
            and target != "card"
        ):
            if new_t and (not old_t or new_t != old_t):
                return m
            m.pop("title", None)
            print(
                "[MODIFY] 仅 title 且无改标题话术且新标题为空或与旧相同，已移除 title",
                flush=True,
            )
            return m

        other_keys = {k for k in m.keys() if k != "title"}
        has_other_field = len(other_keys) > 0

        if batch_mode:
            if not has_title_intent and has_other_field:
                m.pop("title", None)
                print(
                    "[MODIFY] 批量修改：未检测到改标题意图，已移除 title",
                    flush=True,
                )
            return m

        if not has_title_intent and has_other_field:
            m.pop("title", None)
            print(
                "[MODIFY] 用户未明确要求改标题，已移除 title（保留其余字段）",
                flush=True,
            )
        return m

    def _sqlite_path_for_sandbox(self) -> str:
        uri = (self._database_uri or "").strip()
        if uri.startswith("sqlite:///"):
            p = uri.replace("sqlite:///", "", 1)
            return p if os.path.isabs(p) else p
        return "instance/badcase_doctor.db"

    def _perf_modify_trace_context(self, tag: str) -> None:
        """PERF_LOG=1 时打印 ORM 数据源与 subset 所 ATTACH 的 SQLite 路径，便于排查「MySQL 读行 + 本地 db 沙箱」耗时与一致性。"""
        if os.getenv("PERF_LOG", "").strip() != "1":
            return
        uri = (self._database_uri or "").strip()
        if uri.startswith("mysql"):
            orm_kind = "mysql"
        elif uri.startswith("sqlite"):
            orm_kind = "sqlite"
        elif not uri:
            orm_kind = "unset"
        else:
            orm_kind = "other"
        sp = self._sqlite_path_for_sandbox()
        sz_txt = "?"
        try:
            if os.path.isfile(sp):
                sz_txt = f"{os.path.getsize(sp) / (1024 * 1024):.2f}"
        except OSError:
            pass
        note = ""
        if orm_kind == "mysql":
            note = (
                " | NOTE: subset 仍 ATTACH 此 SQLite；文件过大或磁盘慢会拉高 subset_prepare_ms；"
                "若与 MySQL 不同步则写验证语义偏离生产"
            )
        print(
            f"[PERF][modify_trace] {tag} orm_db_kind={orm_kind} "
            f"sandbox_attach_sqlite={sp} sqlite_size_mb={sz_txt}{note}",
            flush=True,
        )

    def _modify_preview_uses_orm_pk_only(
        self, target: str, target_id: Any, project_id: Any
    ) -> bool:
        """已明确定位 id+project 时，读行只需 ORM 主键查询，无需 Text2SQL（避免数秒 LLM，且与生产库一致；Text2SQL 常连本地 SQLite）。"""
        if self._env_flag_enabled("MODIFY_FORCE_TEXT2SQL_ROW_READ", "0"):
            return False
        if target not in ("bug", "badcase", "testcase", "card", "plan"):
            return False
        try:
            if target_id is None or project_id is None:
                return False
            int(target_id)
            int(project_id)
        except (TypeError, ValueError):
            return False
        return True

    def _ensure_text2sql_if_needed_for_preview(
        self,
        prefer_orm_read: bool,
        use_direct_sandbox: bool,
        *,
        target: str = "",
        target_id: Any = None,
        project_id: Any = None,
    ) -> None:
        """沙箱预览：ORM 直读 + 直拼 UPDATE 时无需加载 Text2SQL Agent。"""
        if self._modify_preview_uses_orm_pk_only(target, target_id, project_id):
            return
        if not prefer_orm_read or not use_direct_sandbox:
            self._ensure_text2sql()

    def _get_app_context(self):
        """获取 Flask 应用上下文"""
        from app import app
        return app.app_context()

    def _sqlalchemy_orm_session(self):
        """兼容 ModifyTool(db.session) 与 ModifyTool(db)：统一得到 SQLAlchemy Session / scoped_session。"""
        try:
            return self.db.session
        except AttributeError:
            return self.db

    def _normalize_status(self, status_value: str, target: str) -> str:
        """将中文状态描述映射到数据库定义的英文状态值"""
        status_value = str(status_value).strip().lower()
        
        bug_status_map = {
            '新建': 'new', '新': 'new',
            '已分配': 'assigned', '分配': 'assigned',
            '进行中': 'in_progress', '处理中': 'in_progress',
            '已解决': 'resolved', '解决': 'resolved',
            '已关闭': 'closed', '关闭': 'closed',
            '已重新打开': 'reopened', '重新打开': 'reopened', '重开': 'reopened',
        }
        
        badcase_status_map = {
            '新建': 'new', '新': 'new',
            '待处理': 'pending', '等待': 'pending',
            '已解决': 'resolved', '解决': 'resolved',
            '搁置': 'hold', '暂停': 'hold',
            '已重新打开': 'reopened', '重新打开': 'reopened', '重开': 'reopened', 'reopen': 'reopened',
            '已关闭': 'closed', '关闭': 'closed', 'close': 'closed',
        }
        
        bug_valid_status = ['new', 'assigned', 'in_progress', 'resolved', 'closed', 'reopened']
        badcase_valid_status = ['new', 'pending', 'resolved', 'hold', 'reopened', 'closed', 'not_badcase']
        
        if target == 'bug':
            if status_value in bug_valid_status:
                return status_value
            return bug_status_map.get(status_value, status_value)
        else:
            if status_value in badcase_valid_status:
                return status_value
            return badcase_status_map.get(status_value, status_value)

    @staticmethod
    def _snapshot_status_string(value: Any) -> str:
        """将 ORM/枚举/JSON 中的状态统一为可 diff 的字符串；避免 None/'' 误判为「未设置」而实际库内有值。"""
        if value is None:
            return ""
        if hasattr(value, "value"):
            try:
                inner = getattr(value, "value", None)
                if inner is None:
                    return ""
                return str(inner).strip()
            except Exception:
                pass
        s = str(value).strip()
        if not s or s.lower() == "none":
            return ""
        return s

    def _bug_status_sql_fallback(self, flask_db, bug_id: int, project_id: int) -> str:
        """ORM 偶发未映射到列时，用主键直读 status（与列表/详情一致）。"""
        try:
            from sqlalchemy import text

            r = flask_db.session.execute(
                text(
                    "SELECT status FROM bug WHERE id = :id AND project_id = :pid LIMIT 1"
                ),
                {"id": int(bug_id), "pid": int(project_id)},
            ).fetchone()
            if r and r[0] is not None:
                return self._snapshot_status_string(r[0])
        except Exception as ex:
            print(f"[MODIFY] bug.status SQL fallback failed: {ex}", flush=True)
        return ""

    def _badcase_status_sql_fallback(self, flask_db, badcase_id: int, project_id: int) -> str:
        """BadCase.status 与 ORM 枚举/列不一致时直读库内字符串，避免沙箱旧值被当成空。"""
        try:
            from sqlalchemy import text

            r = flask_db.session.execute(
                text(
                    "SELECT status FROM bad_case WHERE id = :id AND project_id = :pid LIMIT 1"
                ),
                {"id": int(badcase_id), "pid": int(project_id)},
            ).fetchone()
            if r and r[0] is not None:
                return self._snapshot_status_string(r[0])
        except Exception as ex:
            print(f"[MODIFY] badcase.status SQL fallback failed: {ex}", flush=True)
        return ""

    def _testcase_status_sql_fallback(self, flask_db, testcase_id: int, project_id: int) -> str:
        try:
            from sqlalchemy import text

            r = flask_db.session.execute(
                text(
                    "SELECT status FROM test_case WHERE id = :id AND project_id = :pid LIMIT 1"
                ),
                {"id": int(testcase_id), "pid": int(project_id)},
            ).fetchone()
            if r and r[0] is not None:
                return self._snapshot_status_string(r[0])
        except Exception as ex:
            print(f"[MODIFY] testcase.status SQL fallback failed: {ex}", flush=True)
        return ""

    def _enrich_modified_data_for_preview(
        self,
        target: str,
        modified_data: Dict[str, Any],
        modifications: Dict[str, Any],
        project_id: int,
    ) -> None:
        """沙箱预览：负责人等字段的展示名与落库解析一致（原地修改）。"""
        if "assignee" in modifications and target == "badcase":
            from app import User, db as flask_db

            try:
                new_assignee = modifications["assignee"]
                user_id = int(new_assignee)
                user = flask_db.session.query(User).get(user_id)
                modified_data["assignee_display"] = user.name if user else str(new_assignee)
            except (ValueError, TypeError):
                modified_data["assignee_display"] = str(modifications.get("assignee", ""))
        if target in ("bug", "testcase", "card", "plan") and (
            "assignee_id" in modifications or "assignee" in modifications
        ):
            from app import User, db as flask_db

            try:
                raw = (
                    modified_data.get("assignee_id")
                    or modifications.get("assignee_id")
                    or modifications.get("assignee")
                )
                if raw is not None:
                    resolved_uid = self._resolve_user_value(raw, project_id)
                    u = (
                        flask_db.session.query(User).get(int(resolved_uid))
                        if resolved_uid is not None
                        else None
                    )
                    name = u.name if u else str(raw)
                    modified_data["assignee_display"] = name
                    modified_data["assignee"] = name
                    modified_data["assignee_id"] = (
                        int(resolved_uid) if resolved_uid is not None else modified_data.get("assignee_id")
                    )
            except Exception:
                modified_data["assignee_display"] = str(
                    modifications.get("assignee") or modifications.get("assignee_id", "")
                )
                modified_data["assignee"] = modified_data["assignee_display"]

    def _modifications_eligible_for_fast_apply(self, target: str, modifications: Dict[str, Any]) -> bool:
        """仅负责人/状态等低风险字段时允许 skip_preview 直落库（须配合 MODIFY_ALLOW_FAST_APPLY）。"""
        if not modifications:
            return False
        keys = set(modifications.keys())
        if target in ("bug", "testcase"):
            return keys <= {"assignee_id", "status"}
        if target == "badcase":
            return keys <= {"assignee", "status"}
        return False

    def _fetch_original_rows_batch_orm(
        self, target: str, ids: List[int], project_id: int
    ) -> Dict[int, Dict[str, Any]]:
        """一次 IN 查询加载多行（与逐条 _get_original_data ORM 分支字段一致）。"""
        from app import db as flask_db

        ids = [int(x) for x in ids if x is not None]
        if not ids:
            return {}
        out: Dict[int, Dict[str, Any]] = {}
        if target == "bug":
            from app import Bug, User

            rows = (
                flask_db.session.query(Bug)
                .filter(Bug.project_id == project_id, Bug.id.in_(ids))
                .all()
            )
            uids = {r.assignee_id for r in rows if r.assignee_id}
            unames = {}
            if uids:
                for u in flask_db.session.query(User).filter(User.id.in_(uids)).all():
                    unames[u.id] = u.name or ""
            for bug in rows:
                assignee_name = unames.get(bug.assignee_id, "") if bug.assignee_id else ""
                status_snap = self._snapshot_status_string(getattr(bug, "status", None))
                if not status_snap:
                    status_snap = self._bug_status_sql_fallback(flask_db, bug.id, project_id)
                nav_cid = self._nav_card_pk_for_source_orm_row(
                    flask_db.session, "bug", bug, project_id
                )
                out[bug.id] = {
                    "id": bug.id,
                    "title": bug.title,
                    "description": bug.description or "",
                    "status": status_snap,
                    "priority": bug.priority,
                    "severity": bug.severity or "",
                    "assignee_id": bug.assignee_id,
                    "assignee": assignee_name,
                    "plan_id": bug.plan_id,
                    "card_id": nav_cid,
                    "steps_to_reproduce": bug.steps_to_reproduce or "",
                    "expected_result": bug.expected_result or "",
                    "actual_result": bug.actual_result or "",
                }
            return out
        if target == "badcase":
            from app import BadCase

            rows = (
                flask_db.session.query(BadCase)
                .filter(BadCase.project_id == project_id, BadCase.id.in_(ids))
                .all()
            )
            for bc in rows:
                st_snap = self._snapshot_status_string(getattr(bc, "status", None))
                if not st_snap:
                    st_snap = self._badcase_status_sql_fallback(flask_db, bc.id, project_id)
                nav_cid = self._nav_card_pk_for_source_orm_row(
                    flask_db.session, "badcase", bc, project_id
                )
                out[bc.id] = {
                    "id": bc.id,
                    "title": bc.title,
                    "status": st_snap,
                    "priority": bc.priority,
                    "assignee": bc.assignee or "",
                    "plan_id": bc.plan_id,
                    "card_id": nav_cid,
                    "reproduction_steps": bc.reproduction_steps or "",
                    "answer": bc.answer or "",
                    "correct_answer": bc.correct_answer or "",
                    "badcase_result": bc.badcase_result or "",
                    "base_problem": bc.base_problem or "",
                }
            return out
        if target == "testcase":
            from app import TestCase, User

            rows = (
                flask_db.session.query(TestCase)
                .filter(TestCase.project_id == project_id, TestCase.id.in_(ids))
                .all()
            )
            uids = set()
            for r in rows:
                if r.assignee_id:
                    uids.add(r.assignee_id)
                if r.executed_by:
                    uids.add(r.executed_by)
            unames = {}
            if uids:
                for u in flask_db.session.query(User).filter(User.id.in_(uids)).all():
                    unames[u.id] = u.name or ""
            for testcase in rows:
                assignee_name = (
                    unames.get(testcase.assignee_id, "") if testcase.assignee_id else ""
                )
                executed_by_name = (
                    unames.get(testcase.executed_by, "") if testcase.executed_by else ""
                )
                tc_st = self._snapshot_status_string(getattr(testcase, "status", None))
                if not tc_st:
                    tc_st = self._testcase_status_sql_fallback(flask_db, testcase.id, project_id)
                nav_cid = self._nav_card_pk_for_source_orm_row(
                    flask_db.session, "testcase", testcase, project_id
                )
                out[testcase.id] = {
                    "id": testcase.id,
                    "title": testcase.title,
                    "plan_id": testcase.plan_id,
                    "status": tc_st,
                    "case_type": testcase.case_type or "",
                    "priority": testcase.priority or "",
                    "test_type": testcase.test_type or "",
                    "preconditions": testcase.preconditions or "",
                    "steps": json.dumps(testcase.steps, ensure_ascii=False)
                    if testcase.steps
                    else "",
                    "remark": testcase.remark or "",
                    "execution_result": testcase.execution_result.value
                    if testcase.execution_result
                    else "",
                    "assignee_id": testcase.assignee_id,
                    "assignee": assignee_name,
                    "executed_by": executed_by_name,
                    "estimated_time": testcase.estimated_time or "",
                    "actual_time": testcase.actual_time or "",
                    "baseline": testcase.baseline or "",
                    "card_id": nav_cid,
                }
            return out
        return {}

    async def execute(
        self,
        target: str = "bug",
        target_id: int = None,
        modifications: Dict[str, Any] = None,
        project_id: int = None,
        confirm: bool = True,
        natural_query: str = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        执行修改操作
        
        流程：
        1. confirm=False: 沙箱副本预览修改效果
        2. confirm=True: 应用修改到生产库
        
        Args:
            target: 修改目标类型（bug/badcase）
            target_id: 目标ID（可选）
            modifications: 修改内容
            project_id: 项目ID
            confirm: True=应用到生产库, False=沙箱预览
            natural_query: 自然语言查询（用于查找目标记录）
        """
        progress_callback = kwargs.get("progress_callback")
        loc = normalize_locale(kwargs.get("ui_locale"))

        def _progress(msg: Union[str, Dict[str, Any]]):
            if isinstance(msg, dict):
                s = MODIFY_BATCH_ROW_PREFIX + json.dumps(msg, ensure_ascii=False, default=str)
            else:
                s = str(msg)
            print(f"[MODIFY] 进度: {s[:500]}{'…' if len(s) > 500 else ''}", flush=True)
            try:
                if callable(progress_callback):
                    progress_callback(s)
            except Exception:
                pass

        _progress(modify_tool_progress("init", loc))
        from agents.intent.resolution import remap_card_layer_modification_keys

        # 卡片层适配：优先支持 card_id（推荐）；若传入 card_id 且未显式传 target_id，则在源表中反查主键
        card_id = kwargs.get("card_id") or kwargs.get("cardId")
        # 仅传 target_id 但该数字实为 Card 主键时，转为 card_id 并按 Card.source_type 校正 target
        # 注意：Bug/BadCase/TestCase 与 Card 各自自增主键，极易同号；若上游已声明源表且该行存在，禁止覆盖为 card。
        if not card_id and target_id and project_id:
            tl_amb = (str(target or "")).strip().lower()
            skip_card_id_collision = tl_amb in (
                "bug",
                "badcase",
                "testcase",
            ) and self._modify_source_row_exists(tl_amb, target_id, project_id)
            if not skip_card_id_collision:
                amb = self._disambiguate_numeric_id_as_card_id(target_id, project_id)
                if amb is not None:
                    mods_chk = dict(modifications or {})
                    try:
                        # 撞号消解：优先 DB（Card.source_type）+ 字段粗判，避免此处再调 resolve_modify_target_and_id
                        # （否则与 enrich / 下方主路径各打一次 MODIFY_INTENT_LLM）
                        inferred = self._infer_modify_target_from_modification_keys(mods_chk)
                        if inferred in ("bug", "badcase", "testcase"):
                            target = inferred
                            card_id = int(amb)
                            tid_src = self._resolve_target_id_from_card_id(
                                inferred, int(amb), int(project_id)
                            )
                            if tid_src is not None:
                                target_id = int(tid_src)
                        else:
                            canon, _changed = self._normalize_target_using_card_row(
                                str(target or "bug"), project_id, int(amb)
                            )
                            tl = (canon or str(target or "bug")).strip().lower()
                            if tl == "card":
                                target = "card"
                                card_id = int(amb)
                                target_id = int(amb)
                            else:
                                target = tl
                                card_id = int(amb)
                                tid_src = self._resolve_target_id_from_card_id(
                                    tl, int(amb), int(project_id)
                                )
                                if tid_src is not None:
                                    target_id = int(tid_src)
                    except Exception as _ce:
                        print(f"[MODIFY] 撞号消解(DB/字段粗判)失败，回退 resolve: {_ce}", flush=True)
                        try:
                            from agents.intent.resolution import (
                                ModifyResolutionContext,
                                ModifyResolutionError,
                                resolve_modify_target_and_id,
                            )

                            cr_rows = kwargs.get("intent_card_rows")
                            if not isinstance(cr_rows, list):
                                cr_rows = None
                            ctx_hit = ModifyResolutionContext(
                                last_grep_target=str(kwargs.get("intent_last_grep_target") or ""),
                                card_id=int(amb),
                                target_id=target_id,
                                has_raw_bug_list=bool(kwargs.get("intent_has_raw_bug_list")),
                                editing_surface=kwargs.get("editing_surface"),
                                has_raw_badcase_list=bool(kwargs.get("intent_has_raw_badcase_list")),
                                has_raw_testcase_list=bool(kwargs.get("intent_has_raw_testcase_list")),
                                card_rows=cr_rows,
                            )
                            nt, nid, nc = resolve_modify_target_and_id(
                                mods_chk,
                                (kwargs.get("intent_combined_text") or natural_query or "").strip(),
                                ctx_hit,
                            )
                            if nt != "card":
                                target = nt
                                target_id = nid
                                if nc is not None:
                                    card_id = nc
                            else:
                                target = "card"
                                card_id = int(amb)
                                target_id = int(amb)
                        except ModifyResolutionError:
                            target = "card"
                            target_id = int(amb)
                            card_id = int(amb)
                        except Exception as _ce2:
                            print(f"[MODIFY] 撞号消解 resolve 失败，回退为 card: {_ce2}", flush=True)
                            target = "card"
                            target_id = int(amb)
                            card_id = int(amb)
        # 数据层：Card 与 Bug 的 source_* 老数据补全，便于 _normalize_target_using_card_row / 导航
        if card_id and project_id:
            try:
                from app import app as flask_app, db as flask_db, repair_card_source_link_if_missing, Card

                with flask_app.app_context():
                    cid_rep = int(card_id)
                    crow = flask_db.session.query(Card).filter(Card.id == cid_rep).first()
                    if crow is not None:
                        repair_card_source_link_if_missing(crow)
                        flask_db.session.refresh(crow)
            except Exception as _e_rep:
                print(f"[MODIFY] repair_card_source_link_if_missing 跳过: {_e_rep}", flush=True)
        # 传入 card_id 时以 Card.source_type 为权威，避免标题含「testcase」等词误导 LLM 选错 target
        if card_id and project_id:
            target, _ = self._normalize_target_using_card_row(target or "bug", project_id, card_id)
            # 校正 target 为 bug 等后，target_id 可能仍是 Card.id，必须换成源表主键，否则整条链路按「Bug id=卡片 id」误跑
            tl_after = (str(target or "")).strip().lower()
            if (
                tl_after not in ("card", "plan")
                and target_id is not None
            ):
                try:
                    cid_row = int(card_id)
                    tid_cur = int(target_id)
                    if tid_cur == cid_row:
                        tid_src = self._resolve_target_id_from_card_id(
                            tl_after, cid_row, int(project_id)
                        )
                        if tid_src is not None and int(tid_src) != tid_cur:
                            target_id = int(tid_src)
                            print(
                                f"[MODIFY] card_id={cid_row} 已将 target_id 从 Card.id 换为源表主键 {target_id}（target={tl_after}）",
                                flush=True,
                            )
                except (TypeError, ValueError):
                    pass
        # 仅非「纯卡片层」时才把 card_id 解析为源表主键（target=card 时用 Card 主键直接读写）
        if (
            str(target or "").strip().lower() != "card"
            and (not target_id)
            and card_id
            and project_id
        ):
            tid_from_card = self._resolve_target_id_from_card_id(target, card_id, project_id)
            if tid_from_card:
                target_id = tid_from_card
                print(f"[MODIFY] 通过 card_id={card_id} 定位到源表 target_id={target_id}")
        elif str(target or "").strip().lower() == "card" and card_id and project_id and not target_id:
            try:
                target_id = int(card_id)
            except (TypeError, ValueError):
                pass
        batch_target_ids = self._normalize_target_ids(kwargs.get("target_ids", None) or target_id)
        if batch_target_ids:
            target_id = batch_target_ids[0]

        # 目标定位：默认先 ORM 标题模糊匹配，未命中再 Text2SQL（可通过 MODIFY_LOOKUP_ORM_FIRST=0 关闭）
        prefer_orm_lookup = self._env_flag_enabled("MODIFY_LOOKUP_ORM_FIRST", "1")
        if not target_id and natural_query and project_id:
            _progress(modify_tool_progress("orm_fallback", loc))
            tid_fb = self._find_target_by_orm_fallback(target, natural_query, project_id)
            if tid_fb:
                target_id = tid_fb
                print(f"[MODIFY] 通过 ORM 模糊匹配找到目标ID: {target_id}")
        # 已有多条 target_ids 时 target_id 已在上方补齐；勿因 natural_query 加载 Text2SQL（批量预览与定位无关，冷启动数秒）
        if not target_id and natural_query and len(batch_target_ids) <= 1:
            _progress(modify_tool_progress("natural_query_lookup", loc))
            target_id = await self._find_target_by_query(target, natural_query, project_id)
            if target_id:
                print(f"[MODIFY] 通过自然语言查询找到目标ID: {target_id}")

        # 确保 target_id 是整数
        if target_id:
            try:
                target_id = int(target_id)
            except (ValueError, TypeError):
                print(f"[MODIFY] target_id 转换失败: {target_id}")
                return {
                    'success': False,
                    'error': modify_error_target_id_bad(target_id, loc),
                }

        # 已定位源表主键：按 Card / 源表实际类型校正 target，避免 summary 出现「预览修改 BadCase」实为 Bug 行
        db_reconciled_for_resolve = None
        if target_id is not None and project_id is not None:
            tl0 = str(target or "").strip().lower()
            if tl0 not in ("card", "plan"):
                target = self._reconcile_modify_target_from_db(
                    target, target_id, project_id, dict(modifications or {})
                )
                db_reconciled_for_resolve = str(target).strip().lower()
        target = str(target or "bug").strip().lower()
        
        modifications = dict(modifications or {})
        modifications = remap_card_layer_modification_keys(modifications)
        if modifications and len(batch_target_ids) <= 1:
            try:
                from agents.intent.resolution import (
                    ModifyResolutionContext,
                    ModifyResolutionError,
                    normalize_modification_key_set,
                    resolve_modify_target_and_id,
                )

                _fp_now = tuple(sorted(normalize_modification_key_set(modifications)))
                reuse = kwargs.get("intent_resolve_reuse")
                _fp_reuse = reuse.get("mods_fp") if isinstance(reuse, dict) else None
                if isinstance(_fp_reuse, list):
                    _fp_reuse = tuple(_fp_reuse)
                if (
                    isinstance(reuse, dict)
                    and _fp_reuse == _fp_now
                    and reuse.get("resolved_target")
                ):
                    tt = str(reuse["resolved_target"]).strip().lower()
                    nid = reuse.get("resolved_pk")
                    nc = reuse.get("resolved_card_id")
                    print(
                        "[MODIFY] intent_resolve_reuse 命中，跳过二次 resolve_modify_target_and_id | "
                        f"resolved_target={tt!r} resolved_pk={nid!r} resolved_card_id={nc!r} mods_fp={_fp_now!r}",
                        flush=True,
                    )
                else:
                    rc = kwargs.get("intent_result_context")
                    cr_rows = kwargs.get("intent_card_rows")
                    if not isinstance(cr_rows, list) and isinstance(rc, dict):
                        cr_rows = rc.get("grep_modify_raw_card_list") or rc.get("card_list")

                    def _pid(v):
                        if v is None or v == "":
                            return None
                        try:
                            i = int(v)
                            return i if i > 0 else None
                        except (TypeError, ValueError):
                            return None

                    ctx_r = ModifyResolutionContext(
                        last_grep_target=str(kwargs.get("intent_last_grep_target") or ""),
                        card_id=_pid(kwargs.get("card_id") or kwargs.get("cardId") or card_id),
                        target_id=target_id,
                        has_raw_bug_list=bool(kwargs.get("intent_has_raw_bug_list")),
                        editing_surface=kwargs.get("editing_surface"),
                        has_raw_badcase_list=bool(kwargs.get("intent_has_raw_badcase_list")),
                        has_raw_testcase_list=bool(kwargs.get("intent_has_raw_testcase_list")),
                        card_rows=cr_rows if isinstance(cr_rows, list) else None,
                        db_reconciled_target=db_reconciled_for_resolve,
                    )
                    _comb = (kwargs.get("intent_combined_text") or natural_query or "").strip()
                    print(
                        "[MODIFY] resolve_modify_target_and_id 调用前: "
                        f"target_pre={target!r} target_id_pre={target_id!r} card_id_pre={card_id!r} "
                        f"intent_last_grep={kwargs.get('intent_last_grep_target')!r} "
                        f"has_bug/bc/tc_raw={kwargs.get('intent_has_raw_bug_list')}/"
                        f"{kwargs.get('intent_has_raw_badcase_list')}/{kwargs.get('intent_has_raw_testcase_list')} "
                        f"editing_surface={kwargs.get('editing_surface')!r} "
                        f"mod_keys={list(modifications.keys())} "
                        f"card_rows_n={len(cr_rows) if isinstance(cr_rows, list) else 0} "
                        f"combined_len={len(_comb)} combined_head={_comb[:200]!r}",
                        flush=True,
                    )
                    tt, nid, nc = resolve_modify_target_and_id(
                        modifications,
                        _comb,
                        ctx_r,
                    )
                target = str(tt).strip().lower()
                if tt == "card":
                    target_id = nc
                    card_id = nc
                else:
                    target_id = nid
                    if nc is not None:
                        card_id = nc
            except ModifyResolutionError as _mre:
                print(
                    "[MODIFY] resolve_modify_target_and_id 抛出: "
                    f"{_mre!s} | target_id={target_id!r} card_id={card_id!r} target={target!r} "
                    f"mod_keys={list(modifications.keys()) if modifications else []}",
                    flush=True,
                )
                return {
                    "success": False,
                    "error": str(_mre),
                    "hint": str(_mre),
                }
            except Exception as _ie2:
                print(f"[MODIFY] resolve_modify_target_and_id 跳过: {_ie2}", flush=True)

        # resolve / intent_resolve_reuse 仅靠 grep 列表 flag 可能默认 bug；雪花 id 已在 DB 唯一定位源表时以 reconcile 为准
        if (
            db_reconciled_for_resolve
            and db_reconciled_for_resolve in ("bug", "badcase", "testcase")
            and str(target or "").strip().lower() not in ("card", "plan")
            and str(target or "").strip().lower() != db_reconciled_for_resolve
        ):
            print(
                f"[MODIFY] intent 解析 target={target!r} 与 DB 源表唯一命中 {db_reconciled_for_resolve!r} 不一致，采用 DB 结果",
                flush=True,
            )
            target = db_reconciled_for_resolve

        _progress(modify_tool_progress("located_validate", loc, target_id=target_id))
        
        print(
            f"[MODIFY] 开始执行: target={target}, target_id={target_id}, modifications keys={list(modifications.keys())}",
            flush=True,
        )
        if not target_id:
            error_msg, hint_msg = modify_error_missing_params(
                target_id, modifications, target, project_id, loc
            )
            print(f"[MODIFY] ❌ {error_msg}")
            print(f"[MODIFY] 💡 {hint_msg}")
            return {
                'success': False,
                'error': error_msg,
                'hint': hint_msg,
                'need_grep_first': True,  # 标记需要先执行 grep
                'suggested_action': 'grep',
                'suggested_params': {'target': target, 'project_id': project_id}
            }

        # 已定位 target_id 但 modifications 为空：不再报错，返回当前行只读快照（便于「先看详情再改」）
        if len(batch_target_ids) > 1 and not modifications:
            return {
                'success': False,
                'error': modify_error_batch_requires_modifications(loc),
                'hint': modify_message_readonly_no_modifications(loc),
            }

        if not modifications:
            print(
                f"[MODIFY] modifications 为空，返回只读快照 target={target} target_id={target_id}",
                flush=True,
            )
            _progress(modify_tool_progress("readonly_snapshot", loc))
            try:
                with self._get_app_context():
                    original_data = await self._get_original_data(
                        target,
                        target_id,
                        project_id,
                        progress_callback=_progress,
                        ui_locale=loc,
                    )
                    if not original_data:
                        return {
                            'success': False,
                            'error': modify_error_row_not_found(target, target_id, loc),
                        }
                    diff_empty = self._generate_line_diff(
                        original_data, original_data.copy(), [], ui_locale=loc
                    )
                    return {
                        'success': True,
                        'preview_only': True,
                        'readonly_snapshot': True,
                        'confirmation_required': False,
                        'message': modify_message_readonly_no_modifications(loc),
                        'summary': modify_summary_readonly_snapshot(target, target_id, loc),
                        'target': target,
                        'target_id': _json_safe_id(target_id),
                        'before': _json_safe_row(original_data),
                        'after': _json_safe_row(dict(original_data)),
                        'diff': diff_empty,
                        'modifications': {},
                        'sandbox_preview': {
                            'success': True,
                            'skipped': True,
                            'reason': 'no_modifications',
                        },
                    }
            except Exception as e:
                print(f"[MODIFY] 只读快照失败: {e}")
                return {
                    'success': False,
                    'error': modify_error_apply_exception(str(e), loc),
                }
        
        # 字段名映射（LLM 可能返回 owner，需要映射为 assignee）
        normalized_modifications = {}
        for field, value in modifications.items():
            mapped_field = self._map_field_name(field, target)
            normalized_modifications[mapped_field] = value
        modifications = normalized_modifications
        _progress(modify_tool_progress("fields_mapped", loc, keys=list(modifications.keys())))
        
        # 不可修改字段检查：若用户请求修改 type/类型 等，直接返回明确错误，避免长时间执行
        if (target or "").strip().lower() == "plan":
            IMMUTABLE_FIELDS = {
                "id",
                "project_id",
                "created_at",
                "updated_at",
                "creator_id",
                "is_default",
            }
        else:
            IMMUTABLE_FIELDS = {
                "id",
                "type",
                "project_id",
                "plan_id",
                "created_at",
                "updated_at",
                "creator_id",
            }
        requested_immutable = [f for f in modifications.keys() if f in IMMUTABLE_FIELDS]
        if requested_immutable:
            for f in requested_immutable:
                modifications.pop(f, None)
            if not modifications:
                msg, hint = modify_error_immutable_fields(loc)
                print(f"[MODIFY] ❌ {msg}")
                return {
                    'success': False,
                    'error': msg,
                    'immutable_field_rejected': True,
                    'hint': hint
                }
        
        # 状态值映射
        if 'status' in modifications:
            original_status = modifications['status']
            normalized_status = self._normalize_status(modifications['status'], target)
            modifications['status'] = normalized_status
            _progress(
                modify_tool_progress(
                    "status_norm", loc, orig=original_status, norm=normalized_status
                )
            )

        force_fast_commit = (
            self._env_flag_enabled("MODIFY_ALLOW_FAST_APPLY", "0")
            and bool(kwargs.get("skip_preview"))
            and self._modifications_eligible_for_fast_apply(target, modifications)
        )
        if force_fast_commit:
            print(
                "[MODIFY] skip_preview 直落库（无沙箱），需 MODIFY_ALLOW_FAST_APPLY=1 且仅状态/负责人字段",
                flush=True,
            )
        effective_confirm = bool(confirm) or force_fast_commit
        
        try:
            with self._get_app_context():
                if not effective_confirm:
                    prefer_orm_read = self._env_flag_enabled("MODIFY_ORIGINAL_DATA_ORM_FIRST", "1")
                    use_direct_sandbox = self._env_flag_enabled("MODIFY_SANDBOX_DIRECT_SQL", "1")
                    if len(batch_target_ids) > 1:
                        modifications = self._sanitize_title_modifications(
                            target, modifications, None, natural_query, batch_mode=True
                        )
                        return await self._execute_batch_sandbox_preview(
                            target=target,
                            batch_target_ids=batch_target_ids,
                            modifications=modifications,
                            project_id=project_id,
                            loc=loc,
                            _progress=_progress,
                            batch_items=kwargs.get("batch_items"),
                            prefer_orm_read=prefer_orm_read,
                            use_direct_sandbox=use_direct_sandbox,
                        )
                    # confirm=False: 沙箱副本预览（默认 ORM 读行 + 直拼 UPDATE，可按需 Text2SQL）
                    print(f"[MODIFY] 沙箱预览模式，获取原始数据…", flush=True)
                    _perf_single = os.getenv("PERF_LOG", "").strip() == "1"
                    _wall_single0 = time.perf_counter()

                    def _cum_single_ms() -> float:
                        return (time.perf_counter() - _wall_single0) * 1000.0

                    _progress(modify_tool_progress("sandbox_enter", loc))
                    if _perf_single:
                        self._perf_modify_trace_context("single_preview_enter")
                    _t_gate = time.perf_counter()
                    self._ensure_text2sql_if_needed_for_preview(
                        prefer_orm_read,
                        use_direct_sandbox,
                        target=target,
                        target_id=target_id,
                        project_id=project_id,
                    )
                    _gate_ms = (time.perf_counter() - _t_gate) * 1000.0
                    if _perf_single:
                        print(
                            f"[PERF][modify_single_preview] after_text2sql_gate "
                            f"text2sql_gate_ms={_gate_ms:.1f} "
                            f"text2sql_loaded={int(self.text2sql is not None)} "
                            f"prefer_orm_read={int(prefer_orm_read)} direct_sandbox_sql={int(use_direct_sandbox)} "
                            f"cumulative_ms={_cum_single_ms():.1f}",
                            flush=True,
                        )
                    _progress(modify_tool_progress("db_fetch", loc))
                    _t_fetch = time.perf_counter()
                    original_data = await self._get_original_data(
                        target, target_id, project_id, progress_callback=_progress, ui_locale=loc
                    )
                    _fetch_wall_ms = (time.perf_counter() - _t_fetch) * 1000.0
                    if _perf_single:
                        print(
                            f"[PERF][modify_single_preview] after_original_fetch "
                            f"original_fetch_wall_ms={_fetch_wall_ms:.1f} "
                            f"cumulative_ms={_cum_single_ms():.1f}",
                            flush=True,
                        )
                    if not original_data:
                        return {'success': False, 'error': modify_error_row_not_found(target, target_id, loc)}
                    modifications = self._sanitize_title_modifications(
                        target, modifications, original_data, natural_query, batch_mode=False
                    )
                    _progress(modify_tool_progress("sandbox_diff", loc))
                    modified_data = original_data.copy()
                    modified_data.update(modifications)
                    _t_enrich = time.perf_counter()
                    self._enrich_modified_data_for_preview(
                        target, modified_data, modifications, project_id
                    )
                    _enrich_ms = (time.perf_counter() - _t_enrich) * 1000.0
                    _t_ld = time.perf_counter()
                    diff_result = self._generate_line_diff(
                        original_data, modified_data, modifications.keys(), ui_locale=loc
                    )
                    _line_diff_ms = (time.perf_counter() - _t_ld) * 1000.0
                    if _perf_single:
                        print(
                            f"[PERF][modify_single_preview] after_diff "
                            f"enrich_ms={_enrich_ms:.1f} line_diff_ms={_line_diff_ms:.1f} "
                            f"cumulative_ms={_cum_single_ms():.1f}",
                            flush=True,
                        )
                    _progress(modify_tool_progress("sandbox_sql", loc))
                    _t_sbx = time.perf_counter()
                    sandbox_result = await self._preview_in_sandbox(target, target_id, modifications, project_id)
                    _sandbox_ms = (time.perf_counter() - _t_sbx) * 1000.0
                    if _perf_single:
                        print(
                            f"[PERF][modify_single_preview] done "
                            f"sandbox_preview_ms={_sandbox_ms:.1f} "
                            f"sandbox_ok={int(bool(sandbox_result.get('success')))} "
                            f"mode={self._sandbox_preview_mode()} "
                            f"total_wall_ms={_cum_single_ms():.1f}",
                            flush=True,
                        )
                    _progress(modify_tool_progress("sandbox_wait_confirm", loc))
                    mod_summary = modify_modifications_kv_summary(modifications, loc)
                    out_preview = {
                        'success': True, 'confirmation_required': True,
                        'message': modify_message_sandbox_done(loc),
                        'summary': modify_summary_preview(target, target_id, mod_summary, loc),
                        'target': target, 'target_id': _json_safe_id(target_id),
                        'before': _json_safe_row(original_data), 'after': _json_safe_row(modified_data), 'diff': diff_result,
                        'modifications': modifications, 'sandbox_preview': sandbox_result
                    }
                    if isinstance(original_data, dict) and original_data.get("card_id") is not None:
                        out_preview["card_id"] = _json_safe_id(original_data.get("card_id"))
                    return out_preview
                
                # confirm=True: 采纳即落库，快速路径（跳过 Text2SQL 和原始数据获取）
                print(f"[MODIFY] 正在应用修改到数据库（ORM）…", flush=True)
                _progress(modify_tool_progress("commit_start", loc))
                if len(batch_target_ids) > 1:
                    modifications = self._sanitize_title_modifications(
                        target, modifications, None, natural_query, batch_mode=True
                    )
                    success = await self._apply_modifications_batch(
                        target, batch_target_ids, modifications, project_id
                    )
                else:
                    od_apply = await self._get_original_data(
                        target,
                        target_id,
                        project_id,
                        progress_callback=_progress,
                        ui_locale=loc,
                    )
                    modifications = self._sanitize_title_modifications(
                        target, modifications, od_apply, natural_query, batch_mode=False
                    )
                    print(
                        f"[MODIFY_TRACE] commit target={target!r} id={target_id} "
                        f"keys={sorted(modifications.keys())} title_applies={'title' in modifications}",
                        flush=True,
                    )
                    success = await self._apply_modifications(
                        target, target_id, modifications, project_id
                    )
                print(f"[MODIFY] 应用修改完成: success={success}", flush=True)
                _progress(modify_tool_progress("commit_ok" if success else "commit_fail", loc))
                mod_summary = modify_modifications_kv_summary(modifications, loc)
                target_repr = batch_target_ids if len(batch_target_ids) > 1 else target_id
                out_apply = {
                    'success': success,
                    'message': modify_message_apply_ok(target, target_repr, loc)
                    if success
                    else modify_message_apply_fail(loc),
                    'summary': modify_summary_applied(target, target_repr, mod_summary, loc),
                    'target_count': len(batch_target_ids),
                    'before': None, 'after': None, 'diff': None
                }
                if force_fast_commit:
                    out_apply['fast_apply'] = True
                    out_apply['sandbox_skipped'] = True
                return out_apply
            
        except Exception as e:
            print(f"[MODIFY] 错误: {e}")
            return {
                'success': False,
                'error': modify_error_apply_exception(str(e), loc),
            }
    
    def _find_target_by_orm_fallback(self, target: str, natural_query: str, project_id: int) -> Optional[int]:
        """Text2SQL 不可用时：按标题/名称在项目内 LIKE 匹配最近更新的一条记录。"""
        import re

        q = (natural_query or "").strip()
        if not project_id or len(q) < 2:
            return None
        tokens = re.findall(r"[\w\u4e00-\u9fff]+", q)
        needle = None
        for t in tokens:
            if len(t) >= 2:
                needle = t
                break
        if not needle:
            needle = q[:40]
        pat = f"%{needle}%"
        try:
            with self._get_app_context():
                from app import db as flask_db

                if target == "bug":
                    from app import Bug

                    r = (
                        flask_db.session.query(Bug)
                        .filter(Bug.project_id == project_id, Bug.title.like(pat))
                        .order_by(Bug.updated_at.desc())
                        .first()
                    )
                    return r.id if r else None
                if target == "testcase":
                    from app import TestCase

                    r = (
                        flask_db.session.query(TestCase)
                        .filter(TestCase.project_id == project_id, TestCase.title.like(pat))
                        .order_by(TestCase.updated_at.desc())
                        .first()
                    )
                    return r.id if r else None
                from app import BadCase

                r = (
                    flask_db.session.query(BadCase)
                    .filter(BadCase.project_id == project_id, BadCase.title.like(pat))
                    .order_by(BadCase.updated_at.desc())
                    .first()
                )
                return r.id if r else None
        except Exception as e:
            print(f"[MODIFY] ORM fallback 失败: {e}")
            return None

    async def _find_target_by_query(self, target: str, natural_query: str, project_id: int) -> Optional[int]:
        """使用自然语言查询查找目标记录 ID（仅此路径懒加载 Text2SQL，避免批量/已定位请求误触发）。"""
        self._ensure_text2sql()
        if not self.text2sql:
            return None

        try:
            table_map = {"bug": "bug", "badcase": "bad_case", "testcase": "test_case"}
            table_name = table_map.get(target, "bad_case")

            perf_rules = (
                "性能约束："
                "1) 只返回 id 列，严禁 SELECT *；"
                "2) 必须包含 project_id 过滤；"
                "3) 必须包含 LIMIT 1；"
                "4) 尽量使用 title/status/id 等可索引字段过滤；"
                "5) 避免函数包裹列与全表扫描写法。"
            )
            # 关键：明确告诉 Text2SQL 不要把修改目标值当作过滤条件
            intent_hint = (
                "注意：这是修改操作前的定位查询，用户说'改为X'表示修改目标值，"
                "不要把目标值当作过滤条件。例如'状态改为hold'要找的是所有相关记录，"
                "而不是'状态已经是hold'的记录。只根据标题/名称等关键词定位，"
                "不要根据状态/优先级等要修改的字段值过滤。"
            )
            sql_result = self.text2sql.generate_sql(
                f"查找{table_name}表中{natural_query}的记录ID。{intent_hint}{perf_rules}",
                f"项目ID: {project_id}; 仅需返回单条最相关 id"
            )
            
            if sql_result.get('success'):
                exec_result = self.text2sql.execute_sql(sql_result['sql'])
                if exec_result.get('success') and exec_result.get('data'):
                    # 返回第一条记录的ID
                    first_record = exec_result['data'][0]
                    return first_record.get('id')
            
            return None
            
        except Exception as e:
            print(f"[MODIFY] 自然语言查询失败: {e}")
            return None
    
    async def _get_original_data(
        self,
        target: str,
        target_id: int,
        project_id: int,
        progress_callback=None,
        ui_locale: Optional[str] = None,
    ) -> Dict[str, Any]:
        """获取原始数据。progress_callback(msg) 用于流式上报进度。"""
        loc = normalize_locale(ui_locale)

        def _prog(msg: str):
            if callable(progress_callback):
                try:
                    progress_callback(str(msg))
                except Exception:
                    pass

        perf_fetch = os.getenv("PERF_LOG", "").strip() == "1"
        # 默认先 ORM 读行（与生产一致）；需 Text2SQL 时再初始化（MODIFY_ORIGINAL_DATA_ORM_FIRST=0 可改回先 LLM SQL）
        prefer_orm_read = self._env_flag_enabled("MODIFY_ORIGINAL_DATA_ORM_FIRST", "1")
        orm_pk_only = self._modify_preview_uses_orm_pk_only(target, target_id, project_id)
        if perf_fetch and orm_pk_only:
            print(
                f"[PERF][modify_original_fetch] path=orm_pk_fast target={target!r} id={target_id} "
                f"skip_text2sql_row_read=1",
                flush=True,
            )
        if self.text2sql and not prefer_orm_read and not orm_pk_only:
            _prog(modify_tool_progress("text2sql_load", loc))
            _t_t2s0 = time.perf_counter()
            try:
                # 注意：不同 target 对应不同表，testcase 为 test_case
                table_map = {
                    'bug': 'bug',
                    'badcase': 'bad_case',
                    'testcase': 'test_case',
                }
                table_name = table_map.get(target, 'bad_case')
                _tg = time.perf_counter()
                sql_result = self.text2sql.generate_sql(
                    modify_text2sql_row_question(table_name, target_id, loc),
                    f"项目ID: {project_id}" if not is_english_locale(loc) else f"project_id: {project_id}",
                )
                _gen_ms = (time.perf_counter() - _tg) * 1000.0
                _exec_ms = 0.0
                if sql_result.get('success'):
                    _te = time.perf_counter()
                    exec_result = self.text2sql.execute_sql(sql_result['sql'])
                    _exec_ms = (time.perf_counter() - _te) * 1000.0
                    if exec_result.get('success') and exec_result.get('data'):
                        data = exec_result['data'][0]
                        # 补充 assignee 用户名字段（Bug/TestCase 使用 assignee_id，BadCase 使用 assignee）
                        from app import User, db as flask_db
                        if 'assignee_id' in data and data['assignee_id']:
                            # Bug/TestCase: 从用户表获取用户名
                            user = flask_db.session.query(User).get(data['assignee_id'])
                            name = user.name if user else ''
                            data['assignee'] = name
                            data['assignee_display'] = name or modify_assignee_unassigned(loc)
                        elif 'assignee' in data and data.get('assignee'):
                            # BadCase: assignee 存储的是用户ID字符串，需要转换为用户名
                            from app import User
                            try:
                                user_id = int(data['assignee'])
                                user = flask_db.session.query(User).get(user_id)
                                if user:
                                    data['assignee_display'] = user.name
                                    data['assignee_id'] = str(user_id)  # 保存原始用户ID
                                else:
                                    data['assignee_display'] = str(data['assignee'])
                            except (ValueError, TypeError):
                                data['assignee_display'] = str(data['assignee'])
                        else:
                            data['assignee'] = data.get('assignee', '') or ''
                            data['assignee_display'] = modify_assignee_unassigned(loc)
                        if perf_fetch:
                            print(
                                f"[PERF][modify_original_fetch] path=text2sql_first ok=1 "
                                f"gen_sql_ms={_gen_ms:.1f} execute_sql_ms={_exec_ms:.1f} "
                                f"block_wall_ms={(time.perf_counter() - _t_t2s0) * 1000.0:.1f} "
                                f"target={target!r} id={target_id}",
                                flush=True,
                            )
                        return data
                    if perf_fetch:
                        if not exec_result.get("success"):
                            print(
                                f"[PERF][modify_original_fetch] path=text2sql_first ok=0 "
                                f"gen_sql_ms={_gen_ms:.1f} execute_sql_ms={_exec_ms:.1f} "
                                f"reason=execute_failed target={target!r} id={target_id}",
                                flush=True,
                            )
                        else:
                            _rows = len(exec_result.get("data") or [])
                            print(
                                f"[PERF][modify_original_fetch] path=text2sql_first ok=0 "
                                f"gen_sql_ms={_gen_ms:.1f} execute_sql_ms={_exec_ms:.1f} "
                                f"reason=no_rows exec_rows={_rows} target={target!r} id={target_id}",
                                flush=True,
                            )
                elif perf_fetch:
                    print(
                        f"[PERF][modify_original_fetch] path=text2sql_first ok=0 "
                        f"gen_sql_ms={_gen_ms:.1f} reason=generate_failed "
                        f"target={target!r} id={target_id}",
                        flush=True,
                    )
            except Exception as e:
                print(f"[MODIFY] Text2SQL查询失败，回退到ORM: {e}")
                if perf_fetch:
                    print(
                        f"[PERF][modify_original_fetch] path=text2sql_first ok=0 "
                        f"reason=exception err={e!s}",
                        flush=True,
                    )
        
        # ORM 查询（使用 Flask-SQLAlchemy 的 db.session）
        from app import db as flask_db
        _prog(modify_tool_progress("orm_load", loc))
        _t_orm0 = time.perf_counter()

        if target == 'bug':
            _prog(modify_tool_progress("querying_bug", loc))
            from app import Bug, User
            bug = flask_db.session.query(Bug).filter(
                Bug.id == target_id,
                Bug.project_id == project_id
            ).first()
            
            if not bug:
                if perf_fetch:
                    print(
                        f"[PERF][modify_original_fetch] path=orm_bug hit=0 "
                        f"orm_ms={(time.perf_counter() - _t_orm0) * 1000.0:.1f} id={target_id}",
                        flush=True,
                    )
                return None
            
            # 获取负责人用户名
            assignee_name = ''
            if bug.assignee_id:
                user = flask_db.session.query(User).get(bug.assignee_id)
                if user:
                    assignee_name = user.name
            
            if perf_fetch:
                print(
                    f"[PERF][modify_original_fetch] path=orm_bug hit=1 "
                    f"orm_ms={(time.perf_counter() - _t_orm0) * 1000.0:.1f} id={target_id}",
                    flush=True,
                )
            status_snap = self._snapshot_status_string(getattr(bug, "status", None))
            if not status_snap:
                status_snap = self._bug_status_sql_fallback(flask_db, bug.id, project_id)
            nav_card_id = self._nav_card_pk_for_source_orm_row(
                flask_db.session, "bug", bug, project_id
            )
            return {
                'id': bug.id,
                'title': bug.title,
                'description': bug.description or '',
                'status': status_snap,
                'priority': bug.priority,
                'severity': bug.severity or '',
                'assignee_id': bug.assignee_id,
                'assignee': assignee_name,  # 添加用户名字段用于显示
                'plan_id': bug.plan_id,
                'card_id': nav_card_id,
                'steps_to_reproduce': bug.steps_to_reproduce or '',
                'expected_result': bug.expected_result or '',
                'actual_result': bug.actual_result or ''
            }
        
        elif target == 'badcase':
            _prog(modify_tool_progress("querying_badcase", loc))
            from app import BadCase
            badcase = flask_db.session.query(BadCase).filter(
                BadCase.id == target_id,
                BadCase.project_id == project_id
            ).first()
            
            if not badcase:
                return None

            status_snap = self._snapshot_status_string(getattr(badcase, "status", None))
            if not status_snap:
                status_snap = self._badcase_status_sql_fallback(flask_db, badcase.id, project_id)

            nav_card_id = self._nav_card_pk_for_source_orm_row(
                flask_db.session, "badcase", badcase, project_id
            )
            return {
                'id': badcase.id,
                'title': badcase.title,
                'status': status_snap,
                'priority': badcase.priority,
                'assignee': badcase.assignee or '',
                'plan_id': badcase.plan_id,
                'card_id': nav_card_id,
                'reproduction_steps': badcase.reproduction_steps or '',
                'answer': badcase.answer or '',
                'correct_answer': badcase.correct_answer or '',
                'badcase_result': badcase.badcase_result or '',
                'base_problem': badcase.base_problem or ''
            }
        
        elif target == 'testcase':
            _prog(modify_tool_progress("querying_testcase", loc))
            from app import TestCase, User
            testcase = flask_db.session.query(TestCase).filter(
                TestCase.id == target_id,
                TestCase.project_id == project_id
            ).first()
            
            if not testcase:
                return None
            
            assignee_name = ''
            if testcase.assignee_id:
                u = flask_db.session.query(User).get(testcase.assignee_id)
                if u:
                    assignee_name = u.name
            executed_by_name = ''
            if testcase.executed_by:
                user = flask_db.session.query(User).get(testcase.executed_by)
                if user:
                    executed_by_name = user.name
            
            tc_status = self._snapshot_status_string(getattr(testcase, "status", None))
            if not tc_status:
                tc_status = self._testcase_status_sql_fallback(flask_db, testcase.id, project_id)

            nav_card_id = self._nav_card_pk_for_source_orm_row(
                flask_db.session, "testcase", testcase, project_id
            )
            return {
                'id': testcase.id,
                'title': testcase.title,
                'status': tc_status,
                'case_type': testcase.case_type or '',
                'priority': testcase.priority or '',
                'test_type': testcase.test_type or '',
                'preconditions': testcase.preconditions or '',
                'steps': json.dumps(testcase.steps, ensure_ascii=False) if testcase.steps else '',
                'remark': testcase.remark or '',
                'execution_result': testcase.execution_result.value if testcase.execution_result else '',
                'assignee_id': testcase.assignee_id,
                'assignee': assignee_name,
                'executed_by': executed_by_name,
                'estimated_time': testcase.estimated_time or '',
                'actual_time': testcase.actual_time or '',
                'baseline': testcase.baseline or '',
                'plan_id': testcase.plan_id,
                'card_id': nav_card_id,
            }

        elif target == "card":
            _prog(modify_tool_progress("querying_card", loc))
            from app import Card, User

            card = flask_db.session.query(Card).filter(
                Card.id == target_id,
                Card.project_id == project_id,
            ).first()
            if not card:
                return None
            assignee_name = ""
            if card.assignee_id:
                user = flask_db.session.query(User).get(card.assignee_id)
                if user:
                    assignee_name = user.name
            ty = card.type.value if hasattr(card.type, "value") else str(card.type)
            row = {
                "id": card.id,
                "title": card.title,
                "description": card.description or "",
                "type": ty,
                "priority": card.priority or "",
                "plan_id": card.plan_id,
                "assignee_id": card.assignee_id,
                "assignee": assignee_name,
                "source_type": card.source_type,
                "source_id": card.source_id,
            }
            # 卡片表 priority 与源 Bug/BadCase 可能未同步；沙箱「旧值」必须与详情页一致（以源表为准）
            st = (card.source_type or "").strip().lower().replace("-", "_")
            if card.source_id:
                try:
                    sid = int(card.source_id)
                except (TypeError, ValueError):
                    sid = None
                if sid is not None:
                    if st == "bug":
                        from app import Bug

                        bug = (
                            flask_db.session.query(Bug)
                            .filter(Bug.id == sid, Bug.project_id == project_id)
                            .first()
                        )
                        if bug:
                            if bug.priority is not None and str(bug.priority).strip() != "":
                                row["priority"] = str(bug.priority).strip()
                            if bug.severity is not None and str(bug.severity).strip() != "":
                                row["severity"] = bug.severity or ""
                            status_snap = self._snapshot_status_string(getattr(bug, "status", None))
                            if not status_snap:
                                status_snap = self._bug_status_sql_fallback(flask_db, bug.id, project_id)
                            if status_snap:
                                row["status"] = status_snap
                    elif st in ("bad_case", "badcase"):
                        from app import BadCase

                        bc = (
                            flask_db.session.query(BadCase)
                            .filter(BadCase.id == sid, BadCase.project_id == project_id)
                            .first()
                        )
                        if bc:
                            if bc.priority is not None and str(bc.priority).strip() != "":
                                row["priority"] = str(bc.priority).strip()
                            st_bc = self._snapshot_status_string(getattr(bc, "status", None))
                            if not st_bc:
                                st_bc = self._badcase_status_sql_fallback(flask_db, bc.id, project_id)
                            if st_bc:
                                row["status"] = st_bc
                    elif st in ("test_case", "testcase"):
                        from app import TestCase

                        tc = (
                            flask_db.session.query(TestCase)
                            .filter(TestCase.id == sid, TestCase.project_id == project_id)
                            .first()
                        )
                        if tc:
                            if tc.priority is not None and str(tc.priority).strip() != "":
                                row["priority"] = str(tc.priority).strip()
                            st_tc = self._snapshot_status_string(getattr(tc, "status", None))
                            if not st_tc:
                                st_tc = self._testcase_status_sql_fallback(flask_db, tc.id, project_id)
                            if st_tc:
                                row["status"] = st_tc
            # Bug 卡片常见：Card.source 未回填，用 bug.card_id 反查源缺陷状态（与列表/详情一致）
            if not row.get("status") and str(ty).strip().lower() == "bug":
                from app import Bug

                bug_linked = (
                    flask_db.session.query(Bug)
                    .filter(Bug.card_id == card.id, Bug.project_id == project_id)
                    .order_by(Bug.id.asc())
                    .first()
                )
                if bug_linked:
                    status_snap = self._snapshot_status_string(getattr(bug_linked, "status", None))
                    if not status_snap:
                        status_snap = self._bug_status_sql_fallback(flask_db, bug_linked.id, project_id)
                    if status_snap:
                        row["status"] = status_snap
            return row

        elif target == "plan":
            _prog(modify_tool_progress("db_fetch", loc))
            from app import Plan, User

            row = (
                flask_db.session.query(Plan)
                .filter(Plan.id == target_id, Plan.project_id == project_id)
                .first()
            )
            if not row:
                return None
            assignee_name = ""
            if row.assignee_id:
                u = flask_db.session.query(User).get(row.assignee_id)
                if u:
                    assignee_name = u.name or ""
            creator_name = ""
            if row.creator_id:
                u = flask_db.session.query(User).get(row.creator_id)
                if u:
                    creator_name = u.name or ""
            sd = row.start_date.isoformat() if row.start_date else ""
            ed = row.end_date.isoformat() if row.end_date else ""
            return {
                "id": row.id,
                "name": row.name,
                "title": row.name,
                "description": row.description or "",
                "status": row.status or "",
                "priority": row.priority or "",
                "is_pinned": bool(row.is_pinned),
                "is_default": bool(row.is_default),
                "parent_id": row.parent_id,
                "progress": row.progress,
                "scope_notification": bool(row.scope_notification),
                "start_date": sd,
                "end_date": ed,
                "assignee_id": row.assignee_id,
                "assignee": assignee_name,
                "creator_id": row.creator_id,
                "creator": creator_name,
            }

        if self.text2sql and prefer_orm_read and not orm_pk_only:
            _prog(modify_tool_progress("text2sql_load", loc))
            _t_sup0 = time.perf_counter()
            try:
                table_map = {
                    'bug': 'bug',
                    'badcase': 'bad_case',
                    'testcase': 'test_case',
                }
                table_name = table_map.get(target, 'bad_case')
                _tg2 = time.perf_counter()
                sql_result = self.text2sql.generate_sql(
                    modify_text2sql_row_question(table_name, target_id, loc),
                    f"项目ID: {project_id}" if not is_english_locale(loc) else f"project_id: {project_id}",
                )
                _gen2 = (time.perf_counter() - _tg2) * 1000.0
                if sql_result.get('success'):
                    _te2 = time.perf_counter()
                    exec_result = self.text2sql.execute_sql(sql_result['sql'])
                    _ex2 = (time.perf_counter() - _te2) * 1000.0
                    if exec_result.get('success') and exec_result.get('data'):
                        if perf_fetch:
                            print(
                                f"[PERF][modify_original_fetch] path=text2sql_supplement ok=1 "
                                f"gen_sql_ms={_gen2:.1f} execute_sql_ms={_ex2:.1f} "
                                f"block_wall_ms={(time.perf_counter() - _t_sup0) * 1000.0:.1f} "
                                f"target={target!r} id={target_id}",
                                flush=True,
                            )
                        return exec_result['data'][0]
                    if perf_fetch:
                        print(
                            f"[PERF][modify_original_fetch] path=text2sql_supplement ok=0 "
                            f"gen_sql_ms={_gen2:.1f} execute_sql_ms={_ex2:.1f} "
                            f"reason=no_rows target={target!r} id={target_id}",
                            flush=True,
                        )
                elif perf_fetch:
                    print(
                        f"[PERF][modify_original_fetch] path=text2sql_supplement ok=0 "
                        f"gen_sql_ms={_gen2:.1f} reason=generate_failed target={target!r} id={target_id}",
                        flush=True,
                    )
            except Exception as e:
                print(f"[MODIFY] Text2SQL兜底查询失败: {e}")
                if perf_fetch:
                    print(
                        f"[PERF][modify_original_fetch] path=text2sql_supplement ok=0 "
                        f"reason=exception err={e!s}",
                        flush=True,
                    )
        return None
    
    def explore_record(
        self, target: str, target_id: int, project_id: int, ui_locale: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        探索目标记录与可选用户列表，供「思考意图」时使用（类似 Cursor 探索文件）。
        返回当前记录快照 + 用户列表(id/name)，便于大模型结合上下文确认修改意图。
        """
        with self._get_app_context():
            current = self._get_original_data(target, target_id, project_id)
            users = []
            try:
                from app import User
                for u in User.query.filter_by(is_verified=True).limit(100).all():
                    users.append({'id': u.id, 'name': (u.name or '').strip() or str(u.id)})
            except Exception as e:
                print(f"[MODIFY] explore_record 查询用户失败: {e}")
            loc = normalize_locale(ui_locale)
            return {
                'current_record': current,
                'users': users,
                'modifiable_fields': self._get_modifiable_fields(target, loc),
            }
    
    def _get_modifiable_fields(self, target: str, ui_locale: Optional[str] = None) -> List[Dict[str, str]]:
        """返回目标类型可修改的字段列表（英文字段名 + 标签，随 UI 语言）。"""
        return modify_modifiable_fields_rows(target, normalize_locale(ui_locale))
    
    def _generate_line_diff(
        self,
        before: Dict,
        after: Dict,
        changed_fields: List[str],
        ui_locale: Optional[str] = None,
    ) -> List[Dict]:
        """生成行级别差异对比"""
        # 不可修改的字段列表
        immutable_fields = {'id', 'type', 'project_id', 'created_at', 'updated_at', 'creator_id', 'plan_id'}
        loc = normalize_locale(ui_locale)
        
        diff_result = []
        assignee_row_added = False  # 负责人只输出一行，且用 display name，field 统一为 assignee
        
        for field in changed_fields:
            # 跳过不可修改的字段
            if field in immutable_fields:
                print(f"[MODIFY] 跳过不可修改字段: {field}")
                continue
            
            # 负责人：assignee_id/assignee/owner 统一按「显示名」输出为 field='assignee'，便于前端列表展示
            if field in ('assignee_id', 'assignee', 'owner'):
                if assignee_row_added:
                    continue
                assignee_row_added = True
                before_value = str(before.get('assignee_display') or before.get('assignee') or '')
                after_value = str(after.get('assignee_display') or after.get('assignee') or '')
                out_field = 'assignee'
            else:
                before_value = str(before.get(field, ''))
                after_value = str(after.get(field, ''))
                out_field = field
            
            # 构造 diff 行
            parsed_lines = []
            
            # 即使值相同，也显示 delete → add 格式（用户期望看到完整的修改预览）
            if before_value == after_value:
                # 值相同，仍然显示为 delete → add 格式
                parsed_lines.append({
                    'type': 'delete',
                    'content': before_value,
                    'line_no': 0
                })
                parsed_lines.append({
                    'type': 'add',
                    'content': after_value,
                    'line_no': 0
                })
            else:
                # 值不同，使用 difflib 生成详细 diff
                before_lines = before_value.split('\n') if before_value else ['']
                after_lines = after_value.split('\n') if after_value else ['']
                
                differ = difflib.Differ()
                diff_lines = list(differ.compare(before_lines, after_lines))
                
                line_no = 0
                
                for line in diff_lines:
                    if line.startswith('- '):
                        parsed_lines.append({
                            'type': 'delete',
                            'content': line[2:],
                            'line_no': line_no
                        })
                    elif line.startswith('+ '):
                        parsed_lines.append({
                            'type': 'add',
                            'content': line[2:],
                            'line_no': line_no
                        })
                        line_no += 1
                    elif line.startswith('  '):
                        # 对于多行内容中的 unchanged 行，仍然保留
                        parsed_lines.append({
                            'type': 'unchanged',
                            'content': line[2:],
                            'line_no': line_no
                        })
                        line_no += 1
            
            diff_result.append({
                'field': out_field,
                'field_label': modify_field_label(out_field, loc),
                'lines': parsed_lines
            })
        
        return diff_result

    @staticmethod
    def _sandbox_table_name(target: str) -> str:
        return {
            "bug": "bug",
            "badcase": "bad_case",
            "testcase": "test_case",
            "card": "card",
            "plan": "plan",
        }.get(target, "bug")

    @staticmethod
    def _sandbox_preview_mode() -> str:
        """
        沙箱预览执行模式（仅影响 confirm=False 的“写验证”环节，不影响 ORM 读行与 diff 生成）。

        - mysql_temp（默认）：在**同一 MySQL 实例**上 `CREATE TEMPORARY TABLE ... AS SELECT` 拷行后 `UPDATE` 试写；非 MySQL 自动回退 subset（本地 SQLite 子集）
        - subset：只复制“目标表 + 目标行”到临时 SQLite，再 UPDATE
        - full_copy：整库 copy2 后在副本上 UPDATE（最安全，最慢）
        - skip_update：不执行沙箱 UPDATE，仅用 ORM+diff 预览（最快，但无写验证）

        环境变量 / Config.MODIFY_SANDBOX_PREVIEW_MODE：full_copy|subset|mysql_temp|skip_update（默认 mysql_temp：原库临时表试写）。
        可选：MODIFY_SANDBOX_USE_MYSQL_TEMP_WHEN_AVAILABLE=1 且 mode=subset 时，若当前引擎为 MySQL 则走 mysql_temp。
        """
        v = (
            getattr(Config, "MODIFY_SANDBOX_PREVIEW_MODE", None)
            or os.getenv("MODIFY_SANDBOX_PREVIEW_MODE")
            or "mysql_temp"
        ).strip().lower()
        if v in ("full", "fullcopy", "copy", "full_copy"):
            return "full_copy"
        if v in ("subset", "subset_db", "subsetdb"):
            return "subset"
        if v in ("mysql_temp", "mysqltemp", "temp_table", "rdbms_temp", "db_temp"):
            return "mysql_temp"
        if v in ("skip", "skip_update", "skipupdate", "no_update", "noupdate"):
            return "skip_update"
        return "full_copy"

    def _effective_database_uri(self) -> str:
        u = (self._database_uri or "").strip()
        if u:
            return u
        try:
            from flask import current_app

            return str(current_app.config.get("SQLALCHEMY_DATABASE_URI") or "").strip()
        except Exception:
            return ""

    def _is_mysql_bind(self) -> bool:
        try:
            bind = self._sqlalchemy_orm_session().get_bind()
            name = getattr(bind.dialect, "name", "") or ""
            if name == "mysql":
                return True
        except Exception:
            pass
        uri = self._effective_database_uri().lower()
        return uri.startswith("mysql") or "+mysql" in uri

    def _resolve_use_mysql_temp(self, mode: str) -> bool:
        """是否在写验证阶段使用原库 TEMPORARY TABLE（仅 MySQL）。"""
        if not self._is_mysql_bind():
            if mode == "mysql_temp":
                print(
                    "[MODIFY-SANDBOX] mysql_temp 需要 MySQL 连接，当前非 MySQL，将回退 subset / full_copy",
                    flush=True,
                )
            return False
        if mode == "mysql_temp":
            return True
        if mode == "subset" and self._env_flag_enabled(
            "MODIFY_SANDBOX_USE_MYSQL_TEMP_WHEN_AVAILABLE", "0"
        ):
            return True
        return False

    def _mysql_temp_write_validate(
        self,
        target: str,
        target_ids: List[int],
        project_id: int,
        set_clauses: List[str],
        combined_sql_shown: str,
    ) -> Dict[str, Any]:
        """
        在同一 MySQL 连接内：CREATE TEMPORARY TABLE AS SELECT 目标行 → UPDATE 临时表 → DROP。
        不修改业务表；需 CREATE TEMPORARY TABLE / SELECT 权限。
        """
        seen: set[int] = set()
        ids: List[int] = []
        for x in target_ids or []:
            try:
                ix = int(x)
            except (TypeError, ValueError):
                continue
            if ix not in seen:
                seen.add(ix)
                ids.append(ix)
        if not ids or not set_clauses:
            return {"success": False, "error": "mysql_temp: 无有效 id 或可更新字段"}
        table_phys = self._sandbox_table_name(target)
        tmp = f"t_mprev_{uuid.uuid4().hex[:16]}"
        pid = int(project_id)
        in_ph = ",".join(["%s"] * len(ids))
        create_sql = (
            f"CREATE TEMPORARY TABLE `{tmp}` AS "
            f"SELECT * FROM `{table_phys}` WHERE project_id = %s AND id IN ({in_ph})"
        )
        create_params: List[Any] = [pid] + ids
        set_part = ", ".join(set_clauses)
        update_sql = (
            f"UPDATE `{tmp}` SET {set_part} WHERE project_id = %s AND id IN ({in_ph})"
        )
        update_params: List[Any] = [pid] + ids

        perf = os.getenv("PERF_LOG", "").strip() == "1"
        t_wall0 = time.perf_counter()
        get_bind_ms = 0.0
        raw_conn_ms = 0.0
        create_temp_ms = 0.0
        count_ms = 0.0
        update_ms = 0.0
        conn = None
        cur = None
        own_dbapi_connection = False
        dbapi_source = "raw_pool"
        try:
            _tgb = time.perf_counter()
            bind = self._sqlalchemy_orm_session().get_bind()
            get_bind_ms = (time.perf_counter() - _tgb) * 1000.0
            if getattr(bind.dialect, "name", "") != "mysql":
                return {"success": False, "error": "mysql_temp 仅支持 SQLAlchemy MySQL 方言"}
            _trc = time.perf_counter()
            if self._env_flag_enabled("MODIFY_MYSQL_TEMP_REUSE_SESSION_DBAPI", "1"):
                try:
                    sa_conn = self._sqlalchemy_orm_session().connection()
                    fairy = sa_conn.connection
                    _dbapi = getattr(fairy, "driver_connection", None) or getattr(
                        fairy, "dbapi_connection", None
                    )
                    if _dbapi is not None:
                        conn = _dbapi
                        own_dbapi_connection = False
                        dbapi_source = "session"
                except Exception as e:
                    if perf:
                        print(
                            f"[PERF][modify_sandbox] mysql_temp_session_dbapi_fallback err={e!r}",
                            flush=True,
                        )
                    conn = None
            if conn is None:
                conn = bind.raw_connection()
                own_dbapi_connection = True
                dbapi_source = "raw_pool"
            raw_conn_ms = (time.perf_counter() - _trc) * 1000.0
            cur = conn.cursor()
            _tc = time.perf_counter()
            cur.execute(create_sql, create_params)
            create_temp_ms = (time.perf_counter() - _tc) * 1000.0
            _tct = time.perf_counter()
            cur.execute(f"SELECT COUNT(*) FROM `{tmp}`")
            row_cnt = cur.fetchone()[0]
            count_ms = (time.perf_counter() - _tct) * 1000.0
            if int(row_cnt) != len(ids):
                if perf:
                    wall = (time.perf_counter() - t_wall0) * 1000.0
                    print(
                        f"[PERF][modify_sandbox] mysql_temp_segments "
                        f"get_bind_ms={get_bind_ms:.1f} dbapi_acquire_ms={raw_conn_ms:.1f} "
                        f"dbapi_source={dbapi_source} "
                        f"create_temp_ms={create_temp_ms:.1f} count_ms={count_ms:.1f} "
                        f"update_ms=0.0 wall_ms={wall:.1f} "
                        f"table=`{table_phys}` tmp=`{tmp}` n={len(ids)} row_cnt={int(row_cnt)} "
                        f"status=count_mismatch",
                        flush=True,
                    )
                return {
                    "success": False,
                    "error": f"mysql_temp: 临时表 {row_cnt} 行，期望 {len(ids)} 行（检查 id / project_id）",
                }
            _tu = time.perf_counter()
            cur.execute(update_sql, update_params)
            if own_dbapi_connection:
                try:
                    conn.commit()
                except Exception:
                    pass
            update_ms = (time.perf_counter() - _tu) * 1000.0
            if perf:
                wall = (time.perf_counter() - t_wall0) * 1000.0
                print(
                    f"[PERF][modify_sandbox] mysql_temp_segments "
                    f"get_bind_ms={get_bind_ms:.1f} dbapi_acquire_ms={raw_conn_ms:.1f} "
                    f"dbapi_source={dbapi_source} "
                    f"create_temp_ms={create_temp_ms:.1f} count_ms={count_ms:.1f} "
                    f"update_ms={update_ms:.1f} wall_ms={wall:.1f} "
                    f"table=`{table_phys}` tmp=`{tmp}` n={len(ids)} status=ok",
                    flush=True,
                )
            return {
                "success": True,
                "sql": combined_sql_shown,
                "sandbox_mode": True,
                "sandbox_mysql_temp": True,
                "mysql_temp_table": tmp,
                "batch_count": len(ids),
                "message": "沙箱预览完成（原库 TEMPORARY TABLE 试写），确认后将应用到生产库",
                "execution_result": {"success": True, "mysql_temp_table": tmp},
            }
        except Exception as e:
            err_txt = str(e)
            print(f"[MODIFY-SANDBOX] mysql_temp 失败: {err_txt}", flush=True)
            return {"success": False, "error": err_txt or "mysql_temp failed"}
        finally:
            if cur is not None:
                try:
                    cur.execute(f"DROP TEMPORARY TABLE IF EXISTS `{tmp}`")
                except Exception:
                    pass
                try:
                    cur.close()
                except Exception:
                    pass
            if conn is not None and own_dbapi_connection:
                try:
                    conn.commit()
                except Exception:
                    pass
                try:
                    conn.close()
                except Exception:
                    pass

    def _prepare_subset_db_sqlite(
        self, target: str, target_ids: List[int], project_id: int
    ) -> tuple[Optional[str], Optional[str]]:
        """
        轻量子集库：创建一个临时 SQLite 文件，仅包含目标表结构与目标行。
        返回 (subset_db_path, error)。

        注意：该模式用于“写验证”加速，并不追求与生产库完全一致（如触发器/索引/外键等）。
        """
        ids = [int(x) for x in (target_ids or []) if x is not None]
        if not ids:
            return None, "empty target_ids"
        table_name = self._sandbox_table_name(target)
        src_path = self._sqlite_path_for_sandbox()
        try:
            copy_dir = (os.getenv("SANDBOX_DB_COPY_DIR") or "").strip().rstrip("\\/") or tempfile.gettempdir()
            os.makedirs(copy_dir, exist_ok=True)

            subset_path = os.path.join(copy_dir, f"subset_{table_name}.{uuid.uuid4().hex[:10]}.db")
            t0 = time.perf_counter()
            # 建临时库 + 附加源库（只读）
            conn = sqlite3.connect(subset_path)
            try:
                # 降低 IO：临时库可用 WAL/内存 temp_store（仅影响 subset 文件）
                try:
                    conn.execute("PRAGMA journal_mode=WAL;")
                    conn.execute("PRAGMA synchronous=OFF;")
                    conn.execute("PRAGMA temp_store=MEMORY;")
                except Exception:
                    pass
                conn.execute("ATTACH DATABASE ? AS src;", (src_path,))
                # 复制表结构（含列名/类型等），不复制索引/触发器/外键约束
                conn.execute(
                    f"CREATE TABLE main.{table_name} AS SELECT * FROM src.{table_name} WHERE 0;"
                )
                # 仅复制目标行（带 project_id 过滤）
                ph = ",".join(["?"] * len(ids))
                conn.execute(
                    f"INSERT INTO main.{table_name} SELECT * FROM src.{table_name} "
                    f"WHERE project_id = ? AND id IN ({ph});",
                    [int(project_id)] + ids,
                )
                conn.commit()
                conn.execute("DETACH DATABASE src;")
            finally:
                conn.close()
            if os.getenv("PERF_LOG") == "1":
                dt = (time.perf_counter() - t0) * 1000.0
                try:
                    attach_abs = os.path.abspath(os.path.normpath(src_path))
                except OSError:
                    attach_abs = src_path
                print(
                    f"[PERF][modify_sandbox] subset_prepare_ms={dt:.1f} table={table_name} "
                    f"n={len(ids)} attach_src={attach_abs}",
                    flush=True,
                )
            return subset_path, None
        except Exception as e:
            return None, str(e)

    def _exec_update_on_sqlite_path(
        self, db_path: str, sql: str
    ) -> tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
        """在指定 SQLite 文件上执行 UPDATE 预览 SQL（用于 full_copy / subset 两类写验证）。"""
        ok = False
        err_txt: Optional[str] = None
        try:
            conn = sqlite3.connect(db_path)
            try:
                conn.executescript(sql)
                conn.commit()
                ok = True
            except Exception as e:
                err_txt = str(e)
            finally:
                conn.close()
        except Exception as e:
            err_txt = str(e)
        return ok, err_txt, {"batch_local_executescript": True} if ok else None

    def _build_direct_sandbox_set_clauses(
        self, target: str, modifications: Dict[str, Any], project_id: int
    ) -> tuple[Optional[List[str]], Optional[str]]:
        """直出 UPDATE 的 SET 子句列表；与单条沙箱预览语义一致。"""
        if (target or "").strip().lower() == "plan":
            immutable_fields = {
                "id",
                "project_id",
                "created_at",
                "updated_at",
                "creator_id",
                "is_default",
            }
        else:
            immutable_fields = {
                "id",
                "type",
                "project_id",
                "created_at",
                "updated_at",
                "creator_id",
                "plan_id",
            }
        set_clauses: List[str] = []
        for field, value in (modifications or {}).items():
            if field in immutable_fields:
                print(f"[MODIFY-SANDBOX] 跳过不可修改字段: {field}")
                continue
            actual_value = value["new"] if isinstance(value, dict) and "new" in value else value
            field_name = self._map_field_name(field, target)
            if field in ["assignee", "assignee_id", "负责人", "creator", "创建人"] and target != "badcase":
                resolved_value = self._resolve_user_value(actual_value, project_id)
                if resolved_value != actual_value:
                    print(f"[MODIFY-SANDBOX] 用户解析: '{actual_value}' -> 用户ID={resolved_value}")
                    actual_value = resolved_value
            if isinstance(actual_value, str):
                esc = actual_value.replace("'", "''")
                set_clauses.append(f"{field_name} = '{esc}'")
            elif actual_value is None:
                set_clauses.append(f"{field_name} = NULL")
            else:
                set_clauses.append(f"{field_name} = {actual_value}")
        if not set_clauses:
            return None, "没有可更新字段"
        return set_clauses, None

    async def _execute_batch_sandbox_preview(
        self,
        target: str,
        batch_target_ids: List[int],
        modifications: Dict[str, Any],
        project_id: int,
        loc: Optional[str],
        _progress,
        batch_items: Optional[List[Dict[str, Any]]],
        prefer_orm_read: bool,
        use_direct_sandbox: bool,
    ) -> Dict[str, Any]:
        """多条同字段预览：一次 ORM 批量读行 + 逐条 diff（可流式推送）+ 一次沙箱副本批量 UPDATE。"""
        print(
            f"[MODIFY] 批量沙箱预览: n={len(batch_target_ids)} target={target} ids={batch_target_ids}",
            flush=True,
        )
        _progress(modify_tool_progress("sandbox_enter", loc))
        perf = os.getenv("PERF_LOG", "").strip() == "1"
        _wall_batch0 = time.perf_counter()

        def _cum_batch_ms() -> float:
            return (time.perf_counter() - _wall_batch0) * 1000.0

        _t_gate0 = time.perf_counter()
        # 批量预览只走 _fetch_original_rows_batch_orm，从不调用 _get_original_data / Text2SQL；勿懒加载 LLM（可省数秒）
        _text2sql_gate_only_ms = (time.perf_counter() - _t_gate0) * 1000.0
        if perf:
            self._perf_modify_trace_context("batch_preview_enter")
            print(
                f"[PERF][modify_batch] text2sql_gate_ms={_text2sql_gate_only_ms:.1f} "
                f"text2sql_skipped_batch=1 "
                f"prefer_orm_read={int(prefer_orm_read)} direct_sandbox_sql={int(use_direct_sandbox)} "
                f"text2sql_loaded={int(self.text2sql is not None)} "
                f"sandbox_preview_mode={self._sandbox_preview_mode()} "
                f"cumulative_since_batch_start_ms={_cum_batch_ms():.1f}",
                flush=True,
            )

        plan_by_id: Dict[int, Any] = {}
        if batch_items:
            for it in batch_items:
                if isinstance(it, dict) and it.get("id") is not None:
                    try:
                        plan_by_id[int(it["id"])] = it.get("plan_id")
                    except (TypeError, ValueError):
                        pass

        stream_rows = self._env_flag_enabled("MODIFY_BATCH_PREVIEW_STREAM", "1")
        _progress(modify_tool_progress("db_fetch", loc))
        timings: Dict[str, float] = {}
        _t_orm0 = time.perf_counter()
        row_maps = self._fetch_original_rows_batch_orm(target, batch_target_ids, project_id)
        timings["orm_fetch_ms"] = (time.perf_counter() - _t_orm0) * 1000.0
        n_total = len(batch_target_ids)
        if perf:
            try:
                _ids_int = [int(x) for x in batch_target_ids if x is not None]
                _miss = [x for x in _ids_int if x not in row_maps]
            except Exception:
                _miss = []
            print(
                f"[PERF][modify_batch_step] after_orm_fetch "
                f"orm_fetch_ms={timings['orm_fetch_ms']:.1f} "
                f"rows_loaded={len(row_maps)} expected_ids={n_total} "
                f"missing_count={len(_miss)} stream_rows={int(stream_rows)} "
                f"cumulative_ms={_cum_batch_ms():.1f}",
                flush=True,
            )
        all_results: List[Dict[str, Any]] = []
        mod_summary = modify_modifications_kv_summary(modifications, loc)
        enrich_ms_acc = 0.0
        line_diff_ms_acc = 0.0
        batch_row_max_ms = 0.0
        stream_emit_ms_acc = 0.0
        _row_perf_rows: List[str] = []
        _t_diff0 = time.perf_counter()
        for idx, tid in enumerate(batch_target_ids):
            _t_row0 = time.perf_counter()
            tid_i = int(tid)
            original_data = row_maps.get(tid_i)
            if not original_data:
                return {
                    "success": False,
                    "error": modify_error_row_not_found(target, tid_i, loc),
                    "batch_modify": True,
                }
            _progress(modify_tool_progress("sandbox_diff", loc))
            modified_data = original_data.copy()
            modified_data.update(modifications)
            _te0 = time.perf_counter()
            self._enrich_modified_data_for_preview(target, modified_data, modifications, project_id)
            _enrich_one = (time.perf_counter() - _te0) * 1000.0
            enrich_ms_acc += _enrich_one
            _td0 = time.perf_counter()
            diff_result = self._generate_line_diff(
                original_data, modified_data, modifications.keys(), ui_locale=loc
            )
            _diff_one = (time.perf_counter() - _td0) * 1000.0
            line_diff_ms_acc += _diff_one
            _resolved_plan_id = plan_by_id.get(tid_i)
            if _resolved_plan_id is None and isinstance(original_data, dict):
                _rp = original_data.get("plan_id")
                if _rp is not None:
                    try:
                        _resolved_plan_id = int(_rp)
                    except (TypeError, ValueError):
                        _resolved_plan_id = None
            _stream_one = 0.0
            if stream_rows:
                _ts0 = time.perf_counter()
                _progress(
                    {
                        "kind": "batch_preview_row",
                        "index": idx,
                        "total": n_total,
                        "target": target,
                        "target_id": _json_safe_id(tid_i),
                        "plan_id": _json_safe_id(_resolved_plan_id),
                        "record_title": (original_data or {}).get("title"),
                        "diff": diff_result,
                        "before": _json_safe_row(original_data),
                        "after": _json_safe_row(modified_data),
                    }
                )
                _stream_one = (time.perf_counter() - _ts0) * 1000.0
                stream_emit_ms_acc += _stream_one
            _row_wall = (time.perf_counter() - _t_row0) * 1000.0
            batch_row_max_ms = max(batch_row_max_ms, _row_wall)
            if perf:
                try:
                    _dk = list(modifications.keys()) if isinstance(modifications, dict) else []
                except Exception:
                    _dk = []
                _row_perf_rows.append(
                    f"id={tid_i} row_ms={_row_wall:.1f} enrich={_enrich_one:.1f} "
                    f"line_diff={_diff_one:.1f} stream={_stream_one:.1f} mod_fields={_dk[:8]}"
                )
            row_obs: Dict[str, Any] = {
                "success": True,
                "confirmation_required": True,
                "message": modify_message_sandbox_done(loc),
                "summary": modify_summary_preview(target, tid_i, mod_summary, loc),
                "target": target,
                "target_id": _json_safe_id(tid_i),
                "before": _json_safe_row(original_data),
                "after": _json_safe_row(modified_data),
                "diff": diff_result,
                "modifications": modifications,
            }
            if isinstance(original_data, dict) and original_data.get("card_id") is not None:
                row_obs["card_id"] = _json_safe_id(original_data.get("card_id"))
            all_results.append(
                {
                    "id": _json_safe_id(tid_i),
                    "plan_id": _json_safe_id(_resolved_plan_id),
                    "result": row_obs,
                }
            )
        timings["diff_ms"] = (time.perf_counter() - _t_diff0) * 1000.0
        timings["enrich_ms"] = enrich_ms_acc
        timings["line_diff_ms"] = line_diff_ms_acc
        timings["batch_row_max_ms"] = batch_row_max_ms
        timings["stream_emit_ms"] = stream_emit_ms_acc
        timings["text2sql_gate_ms"] = _text2sql_gate_only_ms

        if perf and _row_perf_rows:
            print(
                f"[PERF][modify_batch_step] diff_loop_done "
                f"diff_loop_ms={timings['diff_ms']:.1f} n_rows={len(_row_perf_rows)} "
                f"cumulative_ms={_cum_batch_ms():.1f}",
                flush=True,
            )
            _row_log_cap = 50
            for _ln in _row_perf_rows[:_row_log_cap]:
                print(f"[PERF][modify_batch_row] {_ln}", flush=True)
            if len(_row_perf_rows) > _row_log_cap:
                print(
                    f"[PERF][modify_batch_row] ... truncated "
                    f"shown={_row_log_cap} total={len(_row_perf_rows)}",
                    flush=True,
                )

        if perf:
            try:
                _sp_keys = list((modifications or {}).keys())[:12]
            except Exception:
                _sp_keys = []
            print(
                f"[PERF][modify_batch_step] before_sandbox_write_validate "
                f"cumulative_ms={_cum_batch_ms():.1f} "
                f"modification_keys={_sp_keys}",
                flush=True,
            )

        _progress(modify_tool_progress("sandbox_sql", loc))
        _t_sbx0 = time.perf_counter()
        sandbox_result = await self._preview_in_sandbox_batch(
            target, batch_target_ids, modifications, project_id
        )
        timings["sandbox_preview_ms"] = (time.perf_counter() - _t_sbx0) * 1000.0
        _progress(modify_tool_progress("sandbox_wait_confirm", loc))

        for r in all_results:
            r["result"]["sandbox_preview"] = sandbox_result

        n = len(all_results)
        batch_results_flat: List[Dict[str, Any]] = []
        for r in all_results:
            obs = r["result"]
            br_entry = {
                    "target_id": _json_safe_id(r.get("id")),
                    "plan_id": _json_safe_id(r.get("plan_id")),
                    "target": target,
                    "diff": obs.get("diff", []),
                    "modifications": modifications,
                    "before": _json_safe_row(obs.get("before") or {}),
                    "after": _json_safe_row(obs.get("after") or {}),
                    "confirmation_required": obs.get("confirmation_required", True),
                    "success": obs.get("success", False),
                    "record_title": (obs.get("before") or {}).get("title"),
                    "result": obs,
                }
            if obs.get("card_id") is not None:
                br_entry["card_id"] = obs.get("card_id")
            batch_results_flat.append(br_entry)

        ok = bool(sandbox_result.get("success")) and all(
            r["result"].get("success") for r in all_results
        )
        if perf:
            try:
                _tp = timings.get("text2sql_gate_ms", 0.0)
                _in_loop = (
                    timings.get("enrich_ms", 0.0)
                    + timings.get("line_diff_ms", 0.0)
                    + timings.get("stream_emit_ms", 0.0)
                )
                print(
                    "[PERF][modify_preview] "
                    f"text2sql_gate_ms={_tp:.1f} "
                    f"orm_fetch_ms={timings.get('orm_fetch_ms', 0.0):.1f} "
                    f"diff_loop_ms={timings.get('diff_ms', 0.0):.1f} "
                    f"(enrich_ms={timings.get('enrich_ms', 0.0):.1f} "
                    f"line_diff_ms={timings.get('line_diff_ms', 0.0):.1f} "
                    f"stream_emit_ms={timings.get('stream_emit_ms', 0.0):.1f} "
                    f"batch_row_max_ms={timings.get('batch_row_max_ms', 0.0):.1f} "
                    f"diff_loop_minus_sub_ms={timings.get('diff_ms', 0.0) - _in_loop:.1f}) "
                    f"sandbox_preview_ms={timings.get('sandbox_preview_ms', 0.0):.1f} "
                    f"mode={self._sandbox_preview_mode()} n={n} "
                    f"batch_total_wall_ms={_cum_batch_ms():.1f}",
                    flush=True,
                )
            except Exception:
                pass
        return {
            "success": ok,
            "confirmation_required": True,
            "message": react_batch_modify_preview_message(n, loc),
            "summary": react_batch_modify_summary(n, target, modifications, loc),
            "batch_modify": True,
            "batch_count": n,
            "target": target,
            "results": all_results,
            "batch_results": batch_results_flat,
            "sandbox_preview": sandbox_result,
            "perf": timings,
        }

    async def _preview_in_sandbox_batch(
        self,
        target: str,
        target_ids: List[int],
        modifications: Dict[str, Any],
        project_id: int,
    ) -> Dict[str, Any]:
        """同字段多行：一次副本 + executescript 多条 UPDATE；失败时回退为逐条 _preview_in_sandbox。"""
        use_direct_sql = self._env_flag_enabled("MODIFY_SANDBOX_DIRECT_SQL", "1")
        if os.getenv("PERF_LOG", "").strip() == "1":
            print(
                f"[PERF][modify_sandbox_batch] enter_early "
                f"use_direct_sql={int(use_direct_sql)} n_ids={len(target_ids)} target={target!r}",
                flush=True,
            )
        table_name = self._sandbox_table_name(target)
        if not use_direct_sql:
            last: Optional[Dict[str, Any]] = None
            for tid in target_ids:
                last = await self._preview_in_sandbox(target, tid, modifications, project_id)
            return last or {"success": False, "error": "batch preview empty"}

        set_clauses, err = self._build_direct_sandbox_set_clauses(target, modifications, project_id)
        if err:
            return {"success": False, "error": err}
        assert set_clauses is not None
        stmts = [
            f"UPDATE {table_name} SET {', '.join(set_clauses)} "
            f"WHERE id = {int(tid)} AND project_id = {int(project_id)}"
            for tid in target_ids
        ]
        combined_sql = ";\n".join(stmts) + ";"

        # mode=skip_update：不做写验证（仅给前端展示 diff/preview）
        mode = self._sandbox_preview_mode()
        if os.getenv("PERF_LOG", "").strip() == "1":
            _is_my = self._is_mysql_bind()
            _use_mt = self._resolve_use_mysql_temp(mode)
            if mode == "skip_update":
                _branch = "skip_update"
            elif _use_mt:
                _branch = "mysql_temp"
            elif mode == "subset" or (mode == "mysql_temp" and not _is_my):
                _branch = "subset"
            else:
                _branch = "full_copy"
            print(
                f"[PERF][modify_sandbox_batch] enter "
                f"use_direct_sql={int(use_direct_sql)} mode={mode!r} "
                f"is_mysql_bind={int(_is_my)} mysql_temp_resolved={int(_use_mt)} "
                f"n_ids={len(target_ids)} n_stmts={len(stmts)} "
                f"combined_sql_len={len(combined_sql)} branch={_branch}",
                flush=True,
            )
        if mode == "skip_update":
            return {
                "success": True,
                "sql": combined_sql,
                "sandbox_mode": False,
                "sandbox_skipped": True,
                "message": "已跳过沙箱 UPDATE 写验证（仅预览 diff）",
            }

        if self._resolve_use_mysql_temp(mode):
            _t_mt0 = time.perf_counter()
            res = self._mysql_temp_write_validate(
                target, list(target_ids), project_id, list(set_clauses), combined_sql
            )
            if os.getenv("PERF_LOG", "").strip() == "1":
                print(
                    f"[PERF][modify_sandbox] batch_mysql_temp_ms={(time.perf_counter() - _t_mt0) * 1000.0:.1f} "
                    f"ok={int(bool(res.get('success')))} n={len(target_ids)}",
                    flush=True,
                )
            return res

        # mode=subset：只抽取目标表+目标行到临时库再执行 UPDATE（mysql_temp 不可用则 mysql_temp 模式会回退到此）
        if mode == "subset" or (mode == "mysql_temp" and not self._is_mysql_bind()):
            _t_subset_wall0 = time.perf_counter()
            subset_path, err2 = self._prepare_subset_db_sqlite(target, target_ids, project_id)
            if err2 or not subset_path:
                return {"success": False, "error": f"subset db prepare failed: {err2 or 'unknown'}"}
            try:
                t0 = time.perf_counter()
                ok, err_txt, exec_res = self._exec_update_on_sqlite_path(subset_path, combined_sql)
                if os.getenv("PERF_LOG") == "1":
                    dt = (time.perf_counter() - t0) * 1000.0
                    wall = (time.perf_counter() - _t_subset_wall0) * 1000.0
                    print(
                        f"[PERF][modify_sandbox] subset_exec_ms={dt:.1f} ok={int(bool(ok))} n={len(target_ids)}",
                        flush=True,
                    )
                    print(
                        f"[PERF][modify_sandbox] batch_subset_wall_ms={wall:.1f} n={len(target_ids)} "
                        f"(prepare+log 见 subset_prepare_ms + exec_ms)",
                        flush=True,
                    )
                if not ok:
                    return {"success": False, "error": err_txt or "subset sandbox failed"}
                return {
                    "success": True,
                    "sql": combined_sql,
                    "sandbox_mode": True,
                    "sandbox_subset": True,
                    "batch_count": len(target_ids),
                    "message": "沙箱预览完成（subset 模式），确认后将应用到生产库",
                    "execution_result": {"success": True, **(exec_res or {})},
                }
            finally:
                try:
                    os.unlink(subset_path)
                except OSError:
                    pass

        from agents.tools.text2sql import get_sandbox_executor, SecurityConfig

        sandbox_config = SecurityConfig(db_use_copy=True, db_read_only=False, timeout=30)
        sandbox = get_sandbox_executor(security_config=sandbox_config, fallback_to_local=True)
        db_config = {"path": self._sqlite_path_for_sandbox(), "type": "sqlite"}
        copy_res = sandbox._prepare_db_copy(db_config)
        if not copy_res.get("success"):
            print(f"[MODIFY-SANDBOX-BATCH] 副本失败，回退逐条: {copy_res.get('error')}", flush=True)
            last = None
            for tid in target_ids:
                last = await self._preview_in_sandbox(target, tid, modifications, project_id)
            return last or {"success": False, "error": copy_res.get("error")}

        copy_path = copy_res["copy_path"]
        ok = False
        err_txt: Optional[str] = None
        t_exec0 = time.perf_counter()
        try:
            conn = sqlite3.connect(copy_path)
            try:
                conn.executescript(combined_sql)
                conn.commit()
                ok = True
            except Exception as e:
                err_txt = str(e)
            finally:
                conn.close()
        finally:
            exec_ms = (time.perf_counter() - t_exec0) * 1000.0
            if os.getenv("PERF_LOG") == "1":
                print(
                    f"[PERF][modify_sandbox] batch_executescript_ms={exec_ms:.1f} ok={int(bool(ok))} n={len(target_ids)}",
                    flush=True,
                )

        if not ok:
            print(f"[MODIFY-SANDBOX-BATCH] executescript 失败，尝试在同一副本内逐条执行: {err_txt}", flush=True)
            # 复用同一份副本，逐条执行（避免 N 次整库 copy2）
            last: Optional[Dict[str, Any]] = None
            per_stmt_err: Optional[str] = None
            try:
                conn = sqlite3.connect(copy_path)
                try:
                    for tid, stmt in zip(target_ids, stmts):
                        try:
                            t1 = time.perf_counter()
                            conn.execute(stmt)
                            conn.commit()
                            if os.getenv("PERF_LOG") == "1":
                                dt = (time.perf_counter() - t1) * 1000.0
                                print(
                                    f"[PERF][modify_sandbox] per_stmt_ms={dt:.1f} id={int(tid)}",
                                    flush=True,
                                )
                            last = {"success": True, "sandbox_mode": True, "sql": stmt}
                        except Exception as e:
                            per_stmt_err = str(e)
                            print(
                                f"[MODIFY-SANDBOX-BATCH] 单条执行失败 id={int(tid)} err={per_stmt_err}",
                                flush=True,
                            )
                            break
                finally:
                    conn.close()
            finally:
                try:
                    os.unlink(copy_path)
                except OSError:
                    pass
            if per_stmt_err:
                return {"success": False, "error": per_stmt_err}
            return last or {"success": False, "error": err_txt or "batch sandbox failed"}

        print(f"[MODIFY-SANDBOX-BATCH] 批量 SQL 已执行 n={len(target_ids)}", flush=True)
        try:
            os.unlink(copy_path)
        except OSError:
            pass
        return {
            "success": True,
            "sql": combined_sql,
            "sandbox_mode": True,
            "batch_count": len(target_ids),
            "message": "沙箱预览完成，确认后将应用到生产库",
            "execution_result": {"success": True, "batch_local_executescript": True},
        }
    
    def _partition_card_modifications_for_sandbox_tables(
        self, card_id: int, project_id: int, modifications: Dict[str, Any]
    ) -> Optional[Tuple[str, int, Dict[str, Any], Dict[str, Any]]]:
        """
        target=card 时，将已映射字段名拆成「Card 表可写列」与「关联源表行可写列」。
        若误把 Bug.status 等走 UPDATE card，MySQL 常报 Data truncated（card.status 与 bug 枚举语义不一致或列类型不同）。

        Returns:
            (source_target, source_row_id, source_only_mods, card_only_mods)
            若无法拆分或无需拆分则返回 None。
        """
        if not modifications:
            return None
        try:
            from app import Card

            sess = self._sqlalchemy_orm_session()
            card = (
                sess.query(Card)
                .filter(Card.id == int(card_id), Card.project_id == int(project_id))
                .first()
            )
            if not card:
                return None
            source_target, source_row = self._resolve_linked_source_row_for_card_modify(
                sess, card, project_id
            )
            if not source_row or not source_target:
                return None
            st = str(source_target).strip().lower()
            card_part: Dict[str, Any] = {}
            src_part: Dict[str, Any] = {}
            for field, value in modifications.items():
                if field in {
                    "id",
                    "type",
                    "project_id",
                    "plan_id",
                    "created_at",
                    "updated_at",
                    "creator_id",
                }:
                    continue
                try:
                    if hasattr(card, field):
                        card_part[field] = value
                        continue
                except Exception:
                    pass
                try:
                    mapped = self._map_field_name(field, st)
                    if hasattr(source_row, mapped) or hasattr(source_row, field):
                        src_part[field] = value
                    else:
                        card_part[field] = value
                except Exception:
                    card_part[field] = value
            if not src_part:
                return None
            try:
                sid = int(getattr(source_row, "id", 0) or 0)
            except (TypeError, ValueError):
                sid = 0
            if sid <= 0:
                return None
            return (st, sid, src_part, card_part)
        except Exception as e:
            print(f"[MODIFY-SANDBOX] card 沙箱拆分失败（保持 card 路径）: {e}", flush=True)
            return None

    async def _preview_in_sandbox(self, target: str, target_id: int, modifications: Dict, project_id: int) -> Dict[str, Any]:
        """
        在沙箱副本上预览修改效果
        
        流程：
        1. 创建数据库副本
        2. 在副本上执行 UPDATE SQL
        3. 返回预览结果（不修改生产库）
        """
        try:
            tgt = (target or "").strip().lower()
            if tgt == "card" and modifications:
                split = self._partition_card_modifications_for_sandbox_tables(
                    int(target_id), int(project_id), modifications
                )
                if split:
                    src_tgt, src_id, src_mods, card_mods = split
                    if src_mods and not card_mods:
                        print(
                            f"[MODIFY-SANDBOX] target=card 但字段仅落在源表 {src_tgt} id={src_id}，"
                            f"沙箱 UPDATE 从 card 改为 {self._sandbox_table_name(src_tgt)}",
                            flush=True,
                        )
                        return await self._preview_in_sandbox(
                            src_tgt, int(src_id), src_mods, project_id
                        )
                    if src_mods and card_mods:
                        print(
                            f"[MODIFY-SANDBOX] target=card 字段拆分：card 子集 keys={list(card_mods.keys())} "
                            f"+ {src_tgt} keys={list(src_mods.keys())}，分两次沙箱校验",
                            flush=True,
                        )
                        r_card = await self._preview_in_sandbox(
                            "card", int(target_id), card_mods, project_id
                        )
                        if not r_card.get("success"):
                            return r_card
                        r_src = await self._preview_in_sandbox(
                            src_tgt, int(src_id), src_mods, project_id
                        )
                        if not r_src.get("success"):
                            return r_src
                        sql_a = str(r_card.get("sql") or "").strip()
                        sql_b = str(r_src.get("sql") or "").strip()
                        combined = "\n".join(x for x in (sql_a, sql_b) if x)
                        return {
                            "success": True,
                            "sql": combined,
                            "sandbox_mode": True,
                            "message": "沙箱预览完成（card+源表分表校验），确认后将应用到生产库",
                            "execution_result": {
                                "success": True,
                                "sandbox_card": r_card,
                                "sandbox_source": r_src,
                            },
                        }

            table_name = self._sandbox_table_name(target)
            use_direct_sql = self._env_flag_enabled("MODIFY_SANDBOX_DIRECT_SQL", "1")
            set_clauses, err = self._build_direct_sandbox_set_clauses(target, modifications, project_id)
            if err:
                return {"success": False, "error": err}
            assert set_clauses is not None
            if use_direct_sql:
                sql = (
                    f"UPDATE {table_name} SET {', '.join(set_clauses)} "
                    f"WHERE id = {int(target_id)} AND project_id = {int(project_id)};"
                )
            else:
                if not self.text2sql:
                    return {"success": False, "error": "Text2SQL Agent 未初始化"}
                modify_desc = "、".join(set_clauses)
                nl_query = f"更新{table_name}表中ID为{target_id}的记录，将{modify_desc}"
                context = f"项目ID: {project_id}"
                print(f"[MODIFY-SANDBOX] 沙箱预览: {nl_query}")
                sql_result = self.text2sql.generate_sql(nl_query, context)
                if not sql_result.get("success"):
                    return {
                        "success": False,
                        "error": f"SQL生成失败: {sql_result.get('error')}",
                    }
                sql = sql_result["sql"]
            print(f"[MODIFY-SANDBOX] 生成的SQL: {sql}")

            mode = self._sandbox_preview_mode()
            if mode == "skip_update":
                return {
                    "success": True,
                    "sql": sql,
                    "sandbox_mode": False,
                    "sandbox_skipped": True,
                    "message": "已跳过沙箱 UPDATE 写验证（仅预览 diff）",
                }
            if use_direct_sql and self._resolve_use_mysql_temp(mode):
                return self._mysql_temp_write_validate(
                    target, [int(target_id)], project_id, list(set_clauses), sql.strip()
                )
            if mode == "subset" or (mode == "mysql_temp" and not self._is_mysql_bind()):
                subset_path, err2 = self._prepare_subset_db_sqlite(target, [int(target_id)], project_id)
                if err2 or not subset_path:
                    return {"success": False, "error": f"subset db prepare failed: {err2 or 'unknown'}"}
                try:
                    t0 = time.perf_counter()
                    ok, err_txt, exec_res = self._exec_update_on_sqlite_path(subset_path, sql)
                    if os.getenv("PERF_LOG") == "1":
                        dt = (time.perf_counter() - t0) * 1000.0
                        print(
                            f"[PERF][modify_sandbox] subset_exec_ms={dt:.1f} ok={int(bool(ok))} id={int(target_id)}",
                            flush=True,
                        )
                    if not ok:
                        return {"success": False, "error": err_txt or "subset sandbox failed"}
                    return {
                        "success": True,
                        "sql": sql,
                        "sandbox_mode": True,
                        "sandbox_subset": True,
                        "message": "沙箱预览完成（subset 模式），确认后将应用到生产库",
                        "execution_result": {"success": True, **(exec_res or {})},
                    }
                finally:
                    try:
                        os.unlink(subset_path)
                    except OSError:
                        pass
            
            # 使用沙箱执行器（操作数据库副本）
            from agents.tools.text2sql import get_sandbox_executor, SecurityConfig
            
            # 配置：启用数据库副本模式
            sandbox_config = SecurityConfig(
                db_use_copy=True,      # 使用数据库副本
                db_read_only=False,    # 副本可写
                timeout=15
            )
            # 启用本地回退，当 llm-sandbox 不可用时使用本地执行
            sandbox = get_sandbox_executor(security_config=sandbox_config, fallback_to_local=True)
            
            db_config = {
                "path": self._sqlite_path_for_sandbox(),
                "type": "sqlite",
            }
            
            result = sandbox.execute_sql(sql, db_config, skip_security_check=True)
            
            print(f"[MODIFY-SANDBOX] 沙箱执行结果: success={result.get('success')}")
            
            return {
                "success": result.get("success", False),
                "sql": sql,
                "sandbox_mode": True,
                "message": "沙箱预览完成，确认后将应用到生产库",
                "execution_result": result,
            }
            
        except Exception as e:
            print(f"[MODIFY-SANDBOX] 沙箱预览失败: {e}")
            return {
                "success": False,
                "error": str(e),
            }

    def _normalize_target_ids(self, raw: Any) -> List[int]:
        """将 target_id / target_ids 统一归一化为 int 列表。"""
        if raw is None:
            return []
        vals: List[Any]
        if isinstance(raw, (list, tuple, set)):
            vals = list(raw)
        elif isinstance(raw, str):
            parts = [x.strip() for x in raw.split(",") if x.strip()]
            vals = parts if parts else [raw]
        else:
            vals = [raw]
        out: List[int] = []
        for v in vals:
            try:
                iv = int(v)
            except Exception:
                continue
            if iv not in out:
                out.append(iv)
        return out
    
    async def _apply_modifications(self, target: str, target_id: int, modifications: Dict, project_id: int) -> bool:
        """应用修改到数据库"""
        print(f"[MODIFY] _apply_modifications 开始: target={target}, target_id={target_id}, 共 {len(modifications or {})} 个字段")
        # 不可修改的字段列表（Plan 表无 plan_id / type）
        if (target or "").strip().lower() == "plan":
            immutable_fields = {
                "id",
                "project_id",
                "created_at",
                "updated_at",
                "creator_id",
                "is_default",
            }
        else:
            immutable_fields = {
                "id",
                "type",
                "project_id",
                "created_at",
                "updated_at",
                "creator_id",
                "plan_id",
            }
        
        try:
            # 构建自然语言修改描述
            table_name_map = {
                'bug': 'bug',
                'badcase': 'bad_case',
                'testcase': 'test_case'
            }
            table_name = table_name_map.get(target, 'bug')
            
            # 解析后的修改内容（用于 ORM 回退）
            resolved_modifications = {}
            
            # 构建修改描述
            set_clauses = []
            for field, value in modifications.items():
                # 跳过不可修改的字段
                if field in immutable_fields:
                    print(f"[MODIFY] 跳过不可修改字段: {field}")
                    continue
                
                actual_value = value['new'] if isinstance(value, dict) and 'new' in value else value
                field_name = self._map_field_name(field, target)
                
                # 用户相关字段：解析用户名到用户ID
                # Bug/TestCase 使用 assignee_id（外键），BadCase 使用 assignee（字符串）
                # 用户相关字段：assignee_id 也可能被前端直接传入（但值仍是“用户名/展示名”，不能当作ID直接写）
                if field in ['assignee', 'assignee_id', '负责人', 'creator', '创建人', 'owner']:
                    try:
                        resolved_value = self._resolve_user_value(actual_value, project_id)
                    except Exception as e:
                        # 解析失败：直接中止，避免把“33”误写进 assignee_id 造成未指派
                        print(f"[MODIFY] ❌ 用户解析失败: value={actual_value}, err={e}")
                        raise
                    if resolved_value != actual_value:
                        print(f"[MODIFY] 用户解析: '{actual_value}' -> 用户ID={resolved_value}")
                        actual_value = resolved_value
                    # BadCase 的 assignee 存储字符串形式的用户ID
                    if target == 'badcase' and field in ['assignee', 'assignee_id', '负责人', 'owner']:
                        actual_value = str(actual_value)
                
                # 保存解析后的值
                resolved_modifications[field] = actual_value
                
                if isinstance(actual_value, str):
                    set_clauses.append(f"{field_name}改为'{actual_value}'")
                else:
                    set_clauses.append(f"{field_name}改为{actual_value}")
            
            modify_desc = "、".join(set_clauses)
            print(f"[MODIFY] 正在写入 ORM（commit）…")
            result = await self._apply_modifications_orm(target, target_id, resolved_modifications, project_id)
            print(f"[MODIFY] ORM 写入结果: success={result}")
            return result
            
        except Exception as e:
            print(f"[MODIFY] 应用修改失败: {e}")
            return False

    async def _apply_modifications_batch(self, target: str, target_ids: List[int], modifications: Dict, project_id: int) -> bool:
        """批量更新：同表同字段同值时合并为一条 UPDATE ... WHERE id IN (...)."""
        ids = [int(x) for x in (target_ids or []) if str(x).strip()]
        if not ids:
            return False
        resolved_modifications = {}
        for field, value in (modifications or {}).items():
            actual_value = value['new'] if isinstance(value, dict) and 'new' in value else value
            if field in ['assignee', 'assignee_id', '负责人', 'creator', '创建人', 'owner']:
                actual_value = self._resolve_user_value(actual_value, project_id)
                if target == 'badcase' and field in ['assignee', 'assignee_id', '负责人', 'owner']:
                    actual_value = str(actual_value)
            resolved_modifications[field] = actual_value
        try:
            from app import db as flask_db
            if target == 'bug':
                from app import Bug
                q = flask_db.session.query(Bug).filter(Bug.project_id == project_id, Bug.id.in_(ids))
                update_map = {self._map_field_name(k, target): v for k, v in resolved_modifications.items()}
            elif target == 'badcase':
                from app import BadCase
                q = flask_db.session.query(BadCase).filter(BadCase.project_id == project_id, BadCase.id.in_(ids))
                update_map = {self._map_field_name(k, target): v for k, v in resolved_modifications.items()}
            elif target == 'testcase':
                from app import TestCase
                q = flask_db.session.query(TestCase).filter(TestCase.project_id == project_id, TestCase.id.in_(ids))
                update_map = {self._map_field_name(k, target): v for k, v in resolved_modifications.items()}
            elif target == "card":
                from app import Card

                q = flask_db.session.query(Card).filter(
                    Card.project_id == project_id, Card.id.in_(ids)
                )
                full_map = {
                    self._map_field_name(k, target): v
                    for k, v in resolved_modifications.items()
                }
                card_cols = set(Card.__table__.columns.keys())
                safe_map = {mk: v for mk, v in full_map.items() if mk in card_cols}
                leftover_mods: Dict[str, Any] = {}
                for fk, v in resolved_modifications.items():
                    mk = self._map_field_name(fk, "card")
                    if mk not in card_cols:
                        leftover_mods[fk] = v
                pid = int(project_id)
                affected = 0
                if safe_map:
                    affected = q.update(safe_map, synchronize_session=False) or 0
                any_src = False
                if leftover_mods:
                    for tid in ids:
                        card = (
                            flask_db.session.query(Card)
                            .filter(Card.project_id == pid, Card.id == int(tid))
                            .first()
                        )
                        if card and self._apply_fields_to_card_and_linked_source(
                            flask_db.session, card, leftover_mods, pid
                        ):
                            any_src = True
                if not safe_map and not leftover_mods:
                    return False
                flask_db.session.commit()
                print(
                    f"[MODIFY] 批量更新完成: target={target}, ids={ids}, affected={affected}, source_delegate={any_src}"
                )
                return affected > 0 or any_src
            from app import Bug, BadCase, TestCase

            _model = {"bug": Bug, "badcase": BadCase, "testcase": TestCase}[target]
            for tid in ids:
                row = (
                    flask_db.session.query(_model)
                    .filter(_model.project_id == pid, _model.id == int(tid))
                    .first()
                )
                if row:
                    self._sync_card_from_source_row(
                        flask_db.session, target, row, pid
                    )
            flask_db.session.commit()
            print(f"[MODIFY] 批量更新完成: target={target}, ids={ids}, affected={affected}")
            return affected > 0
        except Exception as e:
            print(f"[MODIFY] 批量更新失败: {e}")
            try:
                flask_db.session.rollback()
            except Exception:
                pass
            return False
    
    def _map_field_name(self, field: str, target: str) -> str:
        """字段名映射 - 将用户/LLM 输入的字段名（含中文）映射到数据库字段名"""
        # Bug 模型使用 assignee_id（外键）
        # BadCase 模型使用 assignee（字符串）
        # TestCase 模型使用 assignee_id（外键）
        
        # 通用映射：owner -> assignee
        common_mapping = {
            'owner': 'assignee',
            '负责人': 'assignee',
        }
        # 详情字段中文 -> 英文（保证 before/after 用同一 key，diff 能取到真实旧值）
        label_to_field = {
            '期望结果': 'expected_result',
            '预期结果': 'expected_result',
            '实际结果': 'actual_result',
            '复现步骤': 'steps_to_reproduce',
            '描述': 'description',
            '标题': 'title',
            '状态': 'status',
            '优先级': 'priority',
            '严重程度': 'severity',
            '相似问题': 'base_problem',
            '答案': 'answer',
            '正确答案': 'correct_answer',
            'BadCase结果': 'badcase_result',
            '解决方式': 'solution',
            '问题原因': 'problem_reason',
            '前置条件': 'preconditions',
            '测试步骤': 'steps',
            '备注': 'remark',
            '基线': 'baseline',
        }
        
        if target == 'badcase':
            field_mapping = {
                **common_mapping,
                **label_to_field,
                'creator': 'creator_id',
                '创建人': 'creator_id',
                'conect_answer': 'answer',
                '最终正确答案': 'correct_answer',
            }
        elif target == "card":
            field_mapping = {
                **common_mapping,
                **label_to_field,
                'assignee': 'assignee_id',
                'creator': 'creator_id',
                '创建人': 'creator_id',
            }
        elif target == "plan":
            plan_labels = dict(label_to_field)
            plan_labels["标题"] = "name"
            plan_labels["名称"] = "name"
            plan_labels["title"] = "name"
            field_mapping = {
                **common_mapping,
                **plan_labels,
                'assignee': 'assignee_id',
                'creator': 'creator_id',
                '创建人': 'creator_id',
            }
        else:
            # bug / testcase
            field_mapping = {
                **common_mapping,
                **label_to_field,
                'assignee': 'assignee_id',
                'creator': 'creator_id',
                '创建人': 'creator_id',
            }
        
        if field in field_mapping:
            return field_mapping[field]
        return field
    
    def _resolve_user_value(self, value: Any, project_id: int = None) -> Any:
        """
        解析用户相关字段的值
        
        优先级：
        1. 先按用户名查询（无论是否数字）
        2. 找不到再尝试当ID用
        
        Args:
            value: 输入值（可能是用户名或用户ID）
            project_id: 项目ID（用于限定用户范围）
            
        Returns:
            用户ID（整数）
        """
        if isinstance(value, int):
            # 即使是整数，也先尝试按用户名查询
            str_value = str(value)
            user_id = self._find_user_by_name(str_value)
            if user_id:
                print(f"[MODIFY] 🔍 整数 '{value}' 匹配到用户名，返回用户ID={user_id}")
                return user_id
            # 没找到，直接返回原值作为ID
            return value
        
        if isinstance(value, str):
            # 先按用户名查询（优先级最高）
            user_id = self._find_user_by_name(value)
            if user_id:
                print(f"[MODIFY] ✅ 用户名 '{value}' -> 用户ID={user_id}")
                return user_id
            
            # 找不到用户，尝试解析为整数ID
            try:
                int_value = int(value)
                # 只有当该 ID 确实存在时，才允许按 ID 解析；否则会把“33”(展示名)误当作 id=33 写入，导致未指派
                try:
                    from app import app, User
                    with app.app_context():
                        exists = User.query.get(int_value) is not None
                except Exception:
                    exists = False
                if exists:
                    print(f"[MODIFY] ⚠️ 未找到用户名 '{value}'，但存在 user.id={int_value}，按ID使用")
                    return int_value
                raise ValueError(f"用户 '{value}' 既不是用户名，也不是有效的用户ID")
            except ValueError:
                pass
            
            # 明确失败：让上层中止写入，避免把错误值写进 assignee_id
            raise ValueError(f"无法解析用户: '{value}'（请使用用户名/邮箱前缀，或有效的用户ID）")
        
        return value
    
    def _find_user_by_name(self, name: str) -> Optional[int]:
        """
        根据用户名查询用户ID
        
        Args:
            name: 用户名
            
        Returns:
            用户ID 或 None
        """
        try:
            from app import app, db, User
            with app.app_context():
                # 1. 精确匹配用户名
                user = User.query.filter(User.name == name).first()
                if user:
                    print(f"[MODIFY] 📌 精确匹配: User.name='{name}' -> id={user.id}")
                    return user.id
                
                # 2. 邮箱前缀匹配
                user = User.query.filter(User.email.ilike(f'{name}@%')).first()
                if user:
                    print(f"[MODIFY] 📧 邮箱匹配: email前缀='{name}' -> id={user.id}")
                    return user.id
                
                # 3. 模糊匹配用户名
                user = User.query.filter(User.name.ilike(f'%{name}%')).first()
                if user:
                    print(f"[MODIFY] 🔍 模糊匹配: name like '%{name}%' -> id={user.id}")
                    return user.id
                
                return None
                
        except Exception as e:
            print(f"[MODIFY] ❌ 查询用户失败: {e}")
            return None
    
    async def _apply_modifications_orm(self, target: str, target_id: int, modifications: Dict, project_id: int) -> bool:
        """ORM 方式应用修改（回退方案）
        
        注意：传入的 modifications 已经是解析后的值（用户名已转换为用户ID）
        """
        # Bug / TestCase / Plan 使用 assignee_id，BadCase 使用 assignee
        if target == 'badcase':
            field_mapping = {
                'creator': 'creator_id',
                '创建人': 'creator_id',
            }
        elif target == "plan":
            field_mapping = {
                'assignee': 'assignee_id',
                '负责人': 'assignee_id',
                'creator': 'creator_id',
                '创建人': 'creator_id',
            }
        else:
            field_mapping = {
                'assignee': 'assignee_id',
                '负责人': 'assignee_id',
                'creator': 'creator_id',
                '创建人': 'creator_id',
            }
        
        try:
            from app import db as flask_db
            
            if target == 'bug':
                from app import Bug
                bug = flask_db.session.query(Bug).filter(
                    Bug.id == target_id,
                    Bug.project_id == project_id
                ).first()
                
                if not bug:
                    return False
                
                for field, value in modifications.items():
                    # 应用字段映射
                    actual_field = field_mapping.get(field, field)
                    
                    if hasattr(bug, actual_field):
                        # 值已经在 _apply_modifications 中解析过了
                        actual_value = value['new'] if isinstance(value, dict) and 'new' in value else value
                        
                        setattr(bug, actual_field, actual_value)
                
                self._sync_card_from_source_row(
                    flask_db.session, "bug", bug, project_id
                )
                flask_db.session.commit()
                return True
            
            elif target == 'badcase':
                from app import BadCase
                badcase = flask_db.session.query(BadCase).filter(
                    BadCase.id == target_id,
                    BadCase.project_id == project_id
                ).first()
                
                if not badcase:
                    return False
                for field, value in modifications.items():
                    actual_field = field_mapping.get(field, field)
                    if hasattr(badcase, actual_field):
                        actual_value = value['new'] if isinstance(value, dict) and 'new' in value else value
                        setattr(badcase, actual_field, actual_value)
                self._sync_card_from_source_row(
                    flask_db.session, "badcase", badcase, project_id
                )
                flask_db.session.commit()
                
                return True
            
            elif target == 'testcase':
                from app import TestCase
                testcase = flask_db.session.query(TestCase).filter(
                    TestCase.id == target_id,
                    TestCase.project_id == project_id
                ).first()
                
                if not testcase:
                    return False
                for field, value in modifications.items():
                    actual_field = field_mapping.get(field, field)
                    if hasattr(testcase, actual_field):
                        actual_value = value['new'] if isinstance(value, dict) and 'new' in value else value
                        setattr(testcase, actual_field, actual_value)
                
                self._sync_card_from_source_row(
                    flask_db.session, "testcase", testcase, project_id
                )
                flask_db.session.commit()
                return True

            elif target == "card":
                from app import Card

                card = flask_db.session.query(Card).filter(
                    Card.id == target_id,
                    Card.project_id == project_id,
                ).first()
                if not card:
                    return False
                applied = self._apply_fields_to_card_and_linked_source(
                    flask_db.session, card, modifications, project_id
                )
                if not applied:
                    print(
                        f"[MODIFY] target=card id={target_id} 无任何可落库字段（Card 与关联源表均未写入）"
                    )
                    return False
                flask_db.session.commit()
                return True

            elif target == "plan":
                from app import Plan

                row = flask_db.session.query(Plan).filter(
                    Plan.id == target_id,
                    Plan.project_id == project_id,
                ).first()
                if not row:
                    return False
                for field, value in modifications.items():
                    actual_field = self._map_field_name(field, target)
                    if not hasattr(row, actual_field):
                        continue
                    actual_value = (
                        value["new"] if isinstance(value, dict) and "new" in value else value
                    )
                    setattr(row, actual_field, actual_value)
                flask_db.session.commit()
                return True

            return False
            
        except Exception as e:
            print(f"[MODIFY] 应用修改失败: {e}")
            flask_db.session.rollback()
            return False
