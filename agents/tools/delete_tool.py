"""
删除 Bug / BadCase / 测试用例 / 迭代卡片(Card) / 迭代计划(Plan) 工具
与 Web API 行为对齐：项目权限、计划删除时的业务约束、工作流通知与计划缓存失效。
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from agents.tool_registry import BaseTool


class DeleteTool(BaseTool):
    """对话删除工作项工具（先预览，confirm=true 再落库）。"""

    def __init__(self, db_session):
        self.db = db_session
        self.name = "delete"
        self.description = """
用于删除 Bug、BadCase、测试用例、**迭代统一卡片 Card** 或 **迭代计划 Plan**。

与 create/modify 相同：默认 **confirm=false** 仅返回待删记录摘要（preview），**不得**未确认就删库。
**confirm=true** 时执行删除；删除计划前须满足与界面一致：非默认计划、无子计划、无关联 Bug/BadCase/用例。

参数：
- target: 'bug' | 'badcase' | 'testcase' | 'card' | 'plan'
- project_id: 项目 ID（必需）
- 主键（按 target 任填其一即可）：
  - bug: target_id 或 bug_id
  - badcase: target_id 或 badcase_id
  - testcase: target_id 或 testcase_id
  - card: card_id 或 target_id（均为 Card 表主键）
  - plan: plan_id
- confirm: 是否执行删除（默认 false，仅预览）

返回：
- confirm=false: preview、confirmation_required=true
- confirm=true: success、deleted_id、message
"""

    @staticmethod
    def _coerce_bool(value, default: bool = False) -> bool:
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value != 0
        if isinstance(value, str):
            s = value.strip().lower()
            if s in ("true", "1", "yes", "on", "是", "确认"):
                return True
            if s in ("false", "0", "no", "off", "否"):
                return False
            return default
        return bool(value)

    @staticmethod
    def _parse_operator_user_id(kwargs: Dict[str, Any]) -> Optional[int]:
        for k in ("user_id", "userId", "operator_user_id"):
            v = kwargs.get(k)
            if v is None or v == "":
                continue
            s = str(v).strip()
            if not s or s.lower() == "system_agent":
                continue
            try:
                return int(s)
            except (TypeError, ValueError):
                continue
        return None

    def _norm_target(self, target: str) -> str:
        t = (target or "bug").strip().lower()
        if t in ("test_case",):
            return "testcase"
        if t in ("bad_case",):
            return "badcase"
        return t

    def _resolve_id(self, target: str, kwargs: Dict[str, Any]) -> Tuple[Optional[int], str]:
        """返回 (id, id_field_name)。"""
        t = self._norm_target(target)
        if t == "bug":
            for k in ("target_id", "bug_id", "id"):
                v = kwargs.get(k)
                if v is not None and str(v).strip() != "":
                    try:
                        return int(v), k
                    except (TypeError, ValueError):
                        pass
        elif t == "badcase":
            for k in ("target_id", "badcase_id", "id"):
                v = kwargs.get(k)
                if v is not None and str(v).strip() != "":
                    try:
                        return int(v), k
                    except (TypeError, ValueError):
                        pass
        elif t == "testcase":
            for k in ("target_id", "testcase_id", "id"):
                v = kwargs.get(k)
                if v is not None and str(v).strip() != "":
                    try:
                        return int(v), k
                    except (TypeError, ValueError):
                        pass
        elif t == "card":
            for k in ("card_id", "target_id", "id"):
                v = kwargs.get(k)
                if v is not None and str(v).strip() != "":
                    try:
                        return int(v), k
                    except (TypeError, ValueError):
                        pass
        elif t == "plan":
            for k in ("plan_id", "id"):
                v = kwargs.get(k)
                if v is not None and str(v).strip() != "":
                    try:
                        return int(v), k
                    except (TypeError, ValueError):
                        pass
        return None, ""

    def _check_project_access(
        self, operator_uid: Optional[int], project_id: int, row_project_id: Any
    ) -> Optional[str]:
        try:
            if int(row_project_id or 0) != int(project_id):
                return "记录所属 project_id 与参数不一致"
        except (TypeError, ValueError):
            return "project_id 比较失败"
        if operator_uid is None:
            return None
        from app import has_project_permission

        if not has_project_permission(operator_uid, int(project_id)):
            return "没有该项目的删除权限"
        return None

    def _plan_delete_block_reason(self, plan) -> Optional[str]:
        from app import Plan

        if getattr(plan, "is_default", False):
            return "默认迭代不能删除"
        if Plan.query.filter_by(parent_id=plan.id).first() is not None:
            return "无法删除包含子计划的计划"
        return None

    def _preview_row(self, target: str, row: Any) -> Dict[str, Any]:
        t = self._norm_target(target)
        if t == "bug":
            return {
                "id": row.id,
                "title": getattr(row, "title", None),
                "project_id": row.project_id,
                "plan_id": getattr(row, "plan_id", None),
            }
        if t == "badcase":
            return {
                "id": row.id,
                "title": getattr(row, "title", None),
                "project_id": row.project_id,
                "plan_id": getattr(row, "plan_id", None),
            }
        if t == "testcase":
            st = getattr(row, "status", None)
            if hasattr(st, "value"):
                st = st.value
            return {
                "id": row.id,
                "title": getattr(row, "title", None),
                "project_id": row.project_id,
                "plan_id": getattr(row, "plan_id", None),
                "status": st,
            }
        if t == "card":
            ct = getattr(row, "type", None)
            if hasattr(ct, "value"):
                ct = ct.value
            return {
                "id": row.id,
                "title": getattr(row, "title", None),
                "type": ct,
                "project_id": row.project_id,
                "plan_id": getattr(row, "plan_id", None),
                "source_type": getattr(row, "source_type", None),
                "source_id": getattr(row, "source_id", None),
            }
        if t == "plan":
            return {
                "id": row.id,
                "name": getattr(row, "name", None),
                "project_id": row.project_id,
                "is_default": getattr(row, "is_default", False),
            }
        return {}

    async def execute(
        self,
        target: str = "bug",
        project_id: int = None,
        confirm: bool = False,
        **kwargs,
    ) -> Dict[str, Any]:
        confirm = self._coerce_bool(confirm, default=False)
        t = self._norm_target(target)
        if t not in ("bug", "badcase", "testcase", "card", "plan"):
            return {"success": False, "error": f"不支持的 target={target!r}"}

        if project_id is None or str(project_id).strip() == "":
            return {"success": False, "error": "缺少 project_id"}

        try:
            pid = int(project_id)
        except (TypeError, ValueError):
            return {"success": False, "error": "project_id 须为整数"}

        rid, _rk = self._resolve_id(t, kwargs)
        if rid is None:
            return {"success": False, "error": "缺少待删除记录的主键（target_id / *_id / plan_id）"}

        operator_uid = self._parse_operator_user_id(kwargs)

        from app import app as flask_app

        with flask_app.app_context():
            from app import (
                BadCase,
                Bug,
                Card,
                Plan,
                TestCase,
                _badcase_status_str,
                _cache_invalidate_plans,
                _schedule_workflow_notify,
                _testcase_status_str,
                _workflow_merge_creator_if_empty,
                _workflow_project_name,
                _workflow_recipients_badcase,
                _workflow_recipients_bug,
                _workflow_recipients_testcase,
            )

            row = None
            if t == "bug":
                row = self.db.query(Bug).get(rid)
                label = "Bug"
            elif t == "badcase":
                row = self.db.query(BadCase).get(rid)
                label = "BadCase"
            elif t == "testcase":
                row = self.db.query(TestCase).get(rid)
                label = "测试用例"
            elif t == "card":
                row = self.db.query(Card).get(rid)
                label = "卡片"
            else:
                row = self.db.query(Plan).get(rid)
                label = "迭代计划"

            if not row:
                return {"success": False, "error": f"{label}不存在（id={rid}）"}

            perm_err = self._check_project_access(operator_uid, pid, row.project_id)
            if perm_err:
                return {"success": False, "error": perm_err}

            if t == "plan":
                reason = self._plan_delete_block_reason(row)
                if reason:
                    return {"success": False, "error": reason}

            preview = {"target": t, "record": self._preview_row(t, row)}

            if not confirm:
                return {
                    "success": True,
                    "confirmation_required": True,
                    "preview": preview,
                    "message": f"将删除{label} #{rid}，请确认后使用 confirm=true",
                }

            # ---- 执行删除（与 app.py DELETE 路由对齐）----
            try:
                if t == "bug":
                    _pid = row.project_id
                    _title = row.title or ""
                    _st = row.status
                    _pn = _workflow_project_name(_pid)
                    _rec = _workflow_merge_creator_if_empty(
                        _workflow_recipients_bug(row), row.creator_id
                    )
                    self.db.session.delete(row)
                    self.db.session.commit()
                    _cache_invalidate_plans(_pid)
                    try:
                        _schedule_workflow_notify(
                            "deleted",
                            "bug",
                            rid,
                            _title,
                            _pid,
                            _pn,
                            _st,
                            None,
                            _rec,
                            actor_id=operator_uid,
                            actor_name="",
                        )
                    except Exception as _e:
                        print(f"[workflow_notify] Bug 删除通知失败: {_e}")
                    return {
                        "success": True,
                        "deleted_id": rid,
                        "target": t,
                        "message": f"已删除 Bug #{rid}",
                    }

                if t == "badcase":
                    _pid = row.project_id
                    _title = row.title or ""
                    _st = _badcase_status_str(row)
                    _pn = _workflow_project_name(_pid)
                    _rec = _workflow_merge_creator_if_empty(
                        _workflow_recipients_badcase(row), row.creator_id
                    )
                    self.db.session.delete(row)
                    self.db.session.commit()
                    _cache_invalidate_plans(_pid)
                    try:
                        _schedule_workflow_notify(
                            "deleted",
                            "badcase",
                            rid,
                            _title,
                            _pid,
                            _pn,
                            _st,
                            None,
                            _rec,
                            actor_id=operator_uid,
                            actor_name="",
                        )
                    except Exception as _e:
                        print(f"[workflow_notify] BadCase 删除通知失败: {_e}")
                    return {
                        "success": True,
                        "deleted_id": rid,
                        "target": t,
                        "message": f"已删除 BadCase #{rid}",
                    }

                if t == "testcase":
                    pid_row = row.project_id
                    _title = row.title or ""
                    _st = _testcase_status_str(row)
                    _pn = _workflow_project_name(pid_row)
                    _rec = _workflow_merge_creator_if_empty(
                        _workflow_recipients_testcase(row), row.creator_id
                    )
                    self.db.session.delete(row)
                    self.db.session.commit()
                    _cache_invalidate_plans(pid_row)
                    try:
                        _schedule_workflow_notify(
                            "deleted",
                            "testcase",
                            rid,
                            _title,
                            pid_row,
                            _pn,
                            _st,
                            None,
                            _rec,
                            actor_id=operator_uid,
                            actor_name="",
                        )
                    except Exception as _e:
                        print(f"[workflow_notify] TestCase 删除通知失败: {_e}")
                    return {
                        "success": True,
                        "deleted_id": rid,
                        "target": t,
                        "message": f"已删除测试用例 #{rid}",
                    }

                if t == "card":
                    self.db.session.delete(row)
                    self.db.session.commit()
                    return {
                        "success": True,
                        "deleted_id": rid,
                        "target": t,
                        "message": f"已删除卡片 #{rid}",
                    }

                # plan
                from app import _detach_plan_work_items

                detached = _detach_plan_work_items(row.id)
                if any(detached.values()):
                    print(f"[DELETE-PLAN] plan_id={row.id} 解绑遗留关联: {detached}", flush=True)
                self.db.session.delete(row)
                self.db.session.commit()
                return {
                    "success": True,
                    "deleted_id": rid,
                    "target": t,
                    "message": f"已删除迭代计划 #{rid}",
                }

            except Exception as e:
                try:
                    self.db.session.rollback()
                except Exception:
                    pass
                print(f"[DELETE] 删除失败: {e}")
                return {"success": False, "error": str(e)}
