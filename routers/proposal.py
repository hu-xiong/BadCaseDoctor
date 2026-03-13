"""
Text2SQL 修改提案相关接口

功能：
- 生成提案：根据传入的 SQL 和过滤条件，在主库上抓取将被影响的行，写入 proposal / proposal_snapshot
- 采纳提案：基于快照做并发/冲突检查后，在主库执行 SQL
- 回滚提案：只修改提案状态为 rolled_back，不直接改数据

说明：
- 当前仅支持对 bug 表生成提案，后续可扩展 bad_case / test_case 等
- 多租户通过 tenant_id 体现，默认使用 "default" 或基于 project_id 生成
"""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Dict, Any, List, Optional

from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from sqlalchemy import text

from agents.tools.sql_preview.preview import preview_auto

proposal_bp = Blueprint("proposal", __name__, url_prefix="/api/proposals")


def _get_app_models():
    """延迟导入，避免与 app 循环依赖"""
    from app import db, Bug, Proposal, ProposalSnapshot, ProposalStatus
    return db, Bug, Proposal, ProposalSnapshot, ProposalStatus


def _get_tenant_id(project_id: int | None = None) -> str:
    """根据 project_id 生成 tenant_id，当前简单使用 default 或 p{project_id}"""
    if project_id:
        return f"p{project_id}"
    return "default"


def _get_active_conflicting_snapshot(target_table: str, row_ids: List[int]):
    """检查是否存在对同一行的未完成提案（用于并发控制）"""
    if not row_ids:
        return None
    db, _Bug, Proposal, ProposalSnapshot, ProposalStatus = _get_app_models()
    active_statuses = [ProposalStatus.PENDING, ProposalStatus.APPROVED]
    return (
        db.session.query(ProposalSnapshot)
        .join(Proposal, Proposal.id == ProposalSnapshot.proposal_id)
        .filter(
            ProposalSnapshot.target_table == target_table,
            ProposalSnapshot.row_id.in_(row_ids),
            Proposal.status.in_(active_statuses),
        )
        .first()
    )


@proposal_bp.route("", methods=["POST"])
@login_required
def create_proposal():
    """
    创建 Text2SQL 修改提案

    请求 JSON 示例：
    {
      "target_table": "bug",
      "project_id": 123,
      "summary": "将项目 123 中状态为 new 的 bug 标记为 in_progress",
      "sql_text": "UPDATE bug SET status='in_progress' WHERE project_id=123 AND status='new';",
      "filter": {
          "project_id": 123,
          "status": "new"
      }
    }
    """
    data = request.get_json(silent=True) or {}

    target_table = (data.get("target_table") or "bug").strip()
    if target_table != "bug":
        return jsonify({"success": False, "error": f"暂仅支持对 bug 表生成提案，收到: {target_table}"}), 400

    project_id = data.get("project_id")
    if not project_id:
        return jsonify({"success": False, "error": "project_id 必填"}), 400

    sql_text = (data.get("sql_text") or "").strip()
    if not sql_text:
        return jsonify({"success": False, "error": "sql_text 必填"}), 400

    summary = (data.get("summary") or "").strip()
    if not summary:
        summary = f"项目 {project_id} 的 bug 修改提案"

    filter_data: Dict[str, Any] = data.get("filter") or {}
    # 新版（方案2通用）：source + sandbox
    src_dialect: str = (data.get("src_dialect") or "mysql").strip().lower()
    source_cfg: Optional[Dict[str, Any]] = data.get("source")
    sandbox_cfg: Optional[Dict[str, Any]] = data.get("sandbox")
    use_scheme2: bool = bool(data.get("use_scheme2")) or bool(source_cfg) or bool(sandbox_cfg)
    preview_limit: int = int(data.get("preview_limit", 50))  # 同 max_rows

    try:
        db, Bug, Proposal, ProposalSnapshot, ProposalStatus = _get_app_models()
        tenant_id = _get_tenant_id(project_id=project_id)
        proposal = Proposal(
            project_id=project_id,
            user_id=current_user.id,
            tenant_id=tenant_id,
            target_table="bug",
            summary=summary,
            sql_text=sql_text,
            affected_rows_estimate=0,
            status=ProposalStatus.PENDING,
            meta={
                "filter": filter_data,
                "source": "text2sql",
            },
        )
        db.session.add(proposal)
        db.session.flush()  # 获取 proposal.id
        snapshots: List[ProposalSnapshot] = []
        scheme2_preview: Dict[str, Any] | None = None

        if use_scheme2:
            # 方案2通用：自动命中行 → 子集 →（可选）云端沙箱预览 + 字段 diff
            sandbox_tenant_id = f"{tenant_id}-proposal-{proposal.id}"
            sandbox_cfg2 = dict(sandbox_cfg or {})
            sandbox_cfg2.setdefault("tenant_id", sandbox_tenant_id)

            scheme2_preview = preview_auto(
                sql=sql_text,
                src_dialect=src_dialect,
                data_source={},  # 兼容字段不用
                source=source_cfg or {},
                sandbox=sandbox_cfg2 or {},
                max_rows=preview_limit,
            )

            diff_obj = (scheme2_preview or {}).get("diff") or {}
            diffs = diff_obj.get("diffs") or []
            # 影响行 ids（仅取 before 存在的行）
            row_ids = [d.get("row_id") for d in diffs if d.get("before") is not None and d.get("row_id") is not None]
            row_ids = [int(x) for x in row_ids]
            if not row_ids:
                return jsonify({"success": False, "error": "方案2未命中任何行（可能 SQL 无 WHERE 或过于复杂），拒绝生成提案"}), 400

            conflicting = _get_active_conflicting_snapshot(target_table="bug", row_ids=row_ids)
            if conflicting:
                return jsonify({
                    "success": False,
                    "error": "存在针对相同行的未完成提案，禁止重复生成",
                    "conflict_proposal_id": conflicting.proposal_id,
                    "conflict_row_id": conflicting.row_id,
                }), 409

            def _parse_dt(v):
                if not v:
                    return None
                if isinstance(v, datetime):
                    return v
                try:
                    return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
                except Exception:
                    return None

            for d in diffs:
                before = d.get("before")
                rid = d.get("row_id")
                if before is None or rid is None:
                    continue
                snapshots.append(ProposalSnapshot(
                    proposal_id=proposal.id,
                    tenant_id=tenant_id,
                    target_table="bug",
                    row_id=int(rid),
                    before_data=before,
                    row_updated_at=_parse_dt(before.get("updated_at")),
                ))

            proposal.affected_rows_estimate = len(snapshots)
            meta = proposal.meta or {}
            meta["scheme2_preview"] = scheme2_preview
            meta["scheme2"] = {"source": bool(source_cfg), "sandbox_tenant_id": sandbox_tenant_id}
            proposal.meta = meta

        else:
            # 旧版：基于 filter 从主库抓取将被影响的行（bug 表）
            query = db.session.query(Bug).filter(Bug.project_id == project_id)
            if "status" in filter_data:
                query = query.filter(Bug.status == filter_data["status"])
            if "ids" in filter_data:
                query = query.filter(Bug.id.in_(filter_data["ids"]))

            rows: List[Bug] = query.all()
            if not rows:
                return jsonify({"success": False, "error": "过滤条件未匹配到任何 Bug，拒绝生成提案"}), 400

            row_ids = [b.id for b in rows]
            conflicting = _get_active_conflicting_snapshot(target_table="bug", row_ids=row_ids)
            if conflicting:
                return jsonify({
                    "success": False,
                    "error": "存在针对相同行的未完成提案，禁止重复生成",
                    "conflict_proposal_id": conflicting.proposal_id,
                    "conflict_row_id": conflicting.row_id,
                }), 409

            for b in rows:
                before = {
                    "id": b.id,
                    "title": b.title,
                    "description": b.description,
                    "status": b.status,
                    "priority": b.priority,
                    "severity": b.severity,
                    "project_id": b.project_id,
                    "plan_id": b.plan_id,
                    "creator_id": b.creator_id,
                    "assignee_id": b.assignee_id,
                    "created_at": b.created_at.isoformat() if b.created_at else None,
                    "updated_at": b.updated_at.isoformat() if b.updated_at else None,
                }
                snapshots.append(ProposalSnapshot(
                    proposal_id=proposal.id,
                    tenant_id=tenant_id,
                    target_table="bug",
                    row_id=b.id,
                    before_data=before,
                    row_updated_at=b.updated_at,
                ))

            proposal.affected_rows_estimate = len(snapshots)

        db.session.bulk_save_objects(snapshots)
        db.session.commit()

        return jsonify({
            "success": True,
            "proposal_id": proposal.id,
            "affected_rows_estimate": proposal.affected_rows_estimate,
            "scheme2_preview": scheme2_preview,
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500


@proposal_bp.route("/<int:proposal_id>/apply", methods=["POST"])
@login_required
def apply_proposal(proposal_id: int):
    """
    采纳并执行提案：
    - 基于 snapshot 做一次并发/冲突检查（row_updated_at 是否变化）
    - 无冲突时，在主库执行 proposal.sql_text
    """
    try:
        db, Bug, Proposal, ProposalSnapshot, ProposalStatus = _get_app_models()
        proposal: Proposal | None = Proposal.query.get(proposal_id)
        if not proposal:
            return jsonify({"success": False, "error": "提案不存在"}), 404

        if proposal.status not in (ProposalStatus.PENDING, ProposalStatus.APPROVED):
            return jsonify({"success": False, "error": f"当前状态不允许执行: {proposal.status.value}"}), 400

        # 仅允许发起人或具有更高权限的用户执行，这里先简单限制为同一用户
        if proposal.user_id != current_user.id:
            return jsonify({"success": False, "error": "仅提案创建者可执行该提案"}), 403

        snapshots = list(proposal.snapshots)
        if not snapshots:
            return jsonify({"success": False, "error": "提案缺少快照数据，无法执行"}), 400

        row_ids = [s.row_id for s in snapshots]

        # 1. 重新从主库抓取当前数据
        bugs = (
            db.session.query(Bug)
            .filter(Bug.id.in_(row_ids))
            .all()
        )
        bug_map: Dict[int, Bug] = {b.id: b for b in bugs}

        # 2. 冲突检查：updated_at 是否和快照时一致
        conflicts: List[Dict[str, Any]] = []
        for s in snapshots:
            cur = bug_map.get(s.row_id)
            if not cur:
                conflicts.append({"row_id": s.row_id, "reason": "已被删除"})
            elif s.row_updated_at and cur.updated_at and cur.updated_at != s.row_updated_at:
                conflicts.append({
                    "row_id": s.row_id,
                    "reason": "已被其他操作修改",
                    "snapshot_updated_at": s.row_updated_at.isoformat() if s.row_updated_at else None,
                    "current_updated_at": cur.updated_at.isoformat() if cur.updated_at else None,
                })

        if conflicts:
            proposal.status = ProposalStatus.CONFLICT
            proposal.has_conflict = True
            db.session.commit()
            return jsonify({
                "success": False,
                "error": "提案与当前数据存在冲突，已标记为 conflict",
                "conflicts": conflicts,
            }), 409

        # 3. 在事务中执行 SQL
        try:
            db.session.execute(text(proposal.sql_text))
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            return jsonify({"success": False, "error": f'执行 SQL 失败: {e}'}), 500

        proposal.status = ProposalStatus.APPLIED
        proposal.applied_at = datetime.utcnow()
        db.session.commit()

        return jsonify({"success": True, "proposal_id": proposal.id})

    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500


@proposal_bp.route("/<int:proposal_id>/rollback", methods=["POST"])
@login_required
def rollback_proposal(proposal_id: int):
    """
    回滚提案：仅修改提案状态为 rolled_back，不自动回滚数据
    """
    try:
        db, Bug, Proposal, ProposalSnapshot, ProposalStatus = _get_app_models()
        proposal: Proposal | None = Proposal.query.get(proposal_id)
        if not proposal:
            return jsonify({"success": False, "error": "提案不存在"}), 404

        if proposal.status != ProposalStatus.APPLIED:
            return jsonify({"success": False, "error": f"仅已执行的提案可标记为回滚，当前状态: {proposal.status.value}"}), 400

        if proposal.user_id != current_user.id:
            return jsonify({"success": False, "error": "仅提案创建者可回滚该提案状态"}), 403

        proposal.status = ProposalStatus.ROLLED_BACK
        proposal.rolled_back_at = datetime.utcnow()
        db.session.commit()

        return jsonify({"success": True, "proposal_id": proposal.id})

    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500

