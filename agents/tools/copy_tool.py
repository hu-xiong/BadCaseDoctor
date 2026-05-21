"""
专用「复制合并」工具：从已有 Bug / BadCase / 测试用例读取并合并业务字段，
生成可直接传入 create 的 fields（不落库）。用于 create 的 copy_from_* 链路易丢参或未合并时的兜底路径。
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from agents.tool_registry import BaseTool
from agents.tools.create_tool import CreateTool
from utils.entity_id import coerce_plausible_entity_pk, is_plausible_entity_pk


class CopyTool(BaseTool):
    """仅做 DB 读取 + 与 CreateTool 相同的校验合并逻辑，不写入数据库。"""

    def __init__(self, db_session):
        self.db = db_session
        self.name = "copy"
        self.description = """
复制类技能（copy_record）中的「属性处理」一步：从已有 Bug / BadCase / 测试用例 / 迭代 Card 读取并合并字段，
生成与 create 共用校验逻辑的 payload（本工具不落库）；下一步由 create 负责 diff 预览与 INSERT。

与 create 的关系：等价于把 create 内部的 copy_from_* 合并逻辑拆成显式工具；可与 grep、create 组合为 grep→copy→create。

适用场景：
- 用户要「按某条记录复制新建」，但 create 未带上 copy_from_* 或合并结果不对；
- 需要先明确合并后的字段，再调用 create 做预览/确认。
- target=card：复制迭代列表里的另一条 Card（copy_from_card_id），合并结果仅含卡片层字段，下一步 create(target='card', fields=...)。

参数：
- target: 'bug' | 'badcase' | 'testcase' | 'card'
- source_id: 源记录数据库主键 id（整数）；card 时为 Card.id
- project_id: 当前项目 id（须与源记录的 project_id 一致）
- title: 可选；新草稿标题，覆盖源标题

亦可不传 source_id，改用别名：copy_from_bug_id、copy_from_card_id、card_id（依 target 而定）。

返回：
- success: 是否成功
- fields: 已校验字段；下一步请调用 create(target=同 target, fields=本字段, confirm=false)，不要再重复填 copy_from_*（fields 已含合并结果）
- target, source_id, next_step: 提示模型后续一步调用 create

注意：复制计划(plan)请仍用 create。
"""

    def _resolve_source_id(self, target: str, kwargs: Dict[str, Any]) -> Optional[Any]:
        direct = kwargs.get("source_id")
        if direct is not None and str(direct).strip() != "":
            return direct
        t = (target or "bug").strip().lower()
        if t == "bug":
            for k in ("copy_from_bug_id", "source_bug_id", "bug_id"):
                v = kwargs.get(k)
                if v is not None and str(v).strip() != "":
                    return v
        elif t == "badcase":
            for k in ("copy_from_badcase_id", "source_badcase_id", "badcase_id"):
                v = kwargs.get(k)
                if v is not None and str(v).strip() != "":
                    return v
        elif t == "testcase":
            for k in ("copy_from_testcase_id", "source_testcase_id", "testcase_id"):
                v = kwargs.get(k)
                if v is not None and str(v).strip() != "":
                    return v
        elif t == "card":
            for k in ("copy_from_card_id", "source_card_id", "card_id"):
                v = kwargs.get(k)
                if v is not None and str(v).strip() != "":
                    return v
        return None

    def _assert_project_match(self, target: str, source_id: int, project_id: int) -> Optional[str]:
        """源记录须属于当前 project_id，避免跨项目误复制。"""
        try:
            pid = int(project_id)
            sid = int(source_id)
        except (TypeError, ValueError):
            return "project_id 或 source_id 无效"
        t = (target or "").strip().lower()
        try:
            if t == "bug":
                from app import Bug as _M

                row = self.db.query(_M).get(sid)
                if not row:
                    return f"未找到 Bug id={sid}"
                if int(row.project_id or 0) != pid:
                    return f"源 Bug 属于 project_id={row.project_id}，与当前项目 {pid} 不一致"
            elif t == "badcase":
                from app import BadCase as _M

                row = self.db.query(_M).get(sid)
                if not row:
                    return f"未找到 BadCase id={sid}"
                if int(row.project_id or 0) != pid:
                    return f"源 BadCase 属于 project_id={row.project_id}，与当前项目 {pid} 不一致"
            elif t == "testcase":
                from app import TestCase as _M

                row = self.db.query(_M).get(sid)
                if not row:
                    return f"未找到测试用例 id={sid}"
                if int(row.project_id or 0) != pid:
                    return f"源用例属于 project_id={row.project_id}，与当前项目 {pid} 不一致"
            elif t == "card":
                from app import Card as _M

                row = self.db.query(_M).get(sid)
                if not row:
                    return f"未找到 Card id={sid}"
                if int(row.project_id or 0) != pid:
                    return f"源 Card 属于 project_id={row.project_id}，与当前项目 {pid} 不一致"
        except Exception as ex:
            return f"校验源记录失败: {ex}"
        return None

    async def execute(
        self,
        target: str = "bug",
        source_id: Any = None,
        project_id: Any = None,
        title: Optional[str] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        kwargs = dict(kwargs or {})

        def _kw_nonempty(v: Any) -> bool:
            return v is not None and str(v).strip() != ""

        # FC 常默认 target=bug；若显式给了卡片复制键，必须按 Card 解析
        if _kw_nonempty(kwargs.get("copy_from_card_id")) or _kw_nonempty(kwargs.get("source_card_id")):
            target = "card"

        sid = source_id if source_id is not None else self._resolve_source_id(target, kwargs)
        if sid is None or str(sid).strip() == "":
            return {"success": False, "error": "缺少 source_id（或 copy_from_*_id / *_id）"}

        sid_int = coerce_plausible_entity_pk(sid)
        if sid_int is None:
            return {
                "success": False,
                "error": (
                    f"source_id={sid!r} 不是有效的雪花主键（过小或无效）。"
                    "请勿从截图猜测小整数 ID；须使用界面上下文 record_id，或先 grep 标题再 copy/create。"
                ),
            }

        if project_id is None or str(project_id).strip() == "":
            return {"success": False, "error": "缺少 project_id"}

        try:
            pid_int = int(project_id)
        except (TypeError, ValueError):
            return {"success": False, "error": "project_id 须为整数"}

        t = (target or "bug").strip().lower()
        if t not in ("bug", "badcase", "testcase", "card"):
            return {"success": False, "error": f"不支持的 target={target!r}，仅支持 bug / badcase / testcase / card"}

        # ReAct 常在异步/线程池调用工具，须全程包裹 app_context（校验 project 与 ORM 合并都依赖 Flask-SQLAlchemy）
        from app import app as flask_app

        create = CreateTool(self.db)
        with flask_app.app_context():
            mismatch = self._assert_project_match(t, sid_int, pid_int)
            # 模型把迭代卡片标题 bug1.x 误当成缺陷：id 实为 Card 主键
            if mismatch and t == "bug" and isinstance(mismatch, str) and mismatch.startswith("未找到 Bug"):
                from app import Card as _CardRow

                row_c = self.db.query(_CardRow).get(sid_int)
                if row_c is not None and int(row_c.project_id or 0) == pid_int:
                    t = "card"
                    mismatch = self._assert_project_match(t, sid_int, pid_int)
            if mismatch:
                return {"success": False, "error": mismatch}

            fields: Dict[str, Any] = {}
            if t == "bug":
                fields["copy_from_bug_id"] = sid_int
            elif t == "badcase":
                fields["copy_from_badcase_id"] = sid_int
            elif t == "testcase":
                fields["copy_from_testcase_id"] = sid_int
            else:
                fields["copy_from_card_id"] = sid_int

            if title is not None and str(title).strip() != "":
                fields["title"] = title

            try:
                validated = create._validate_and_complete_fields(t, fields, pid_int)
            except ValueError as e:
                return {"success": False, "error": str(e)}
            except Exception as e:
                return {"success": False, "error": f"合并字段失败: {e}"}

        label = create._get_target_label(t)
        return {
            "success": True,
            "message": f"已从源{label} #{sid_int} 合并字段；请下一步调用 create 预览创建（不落库）。",
            "target": t,
            "source_id": sid_int,
            "fields": validated,
            "next_step": "调用 create：target 与本响应一致；params.fields = 本响应的 fields；confirm=false 预览；用户确认后再 confirm=true。无需再填 copy_from_*。",
        }
