"""card_history_api（自 app.py 拆出）。"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta, timezone

from flask import (
    Blueprint,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import login_required, login_user, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash

card_history_bp = Blueprint("card_history", __name__)


def _app():
    import app as _application
    return _application


@login_required
def api_get_card_plan_history(card_id):
    """获取卡片的计划变更历史"""
    print(f"=== 获取卡片 {card_id} 的计划变更历史 ===")
    
    try:
        card = Card.query.get_or_404(card_id)
        
        if not has_project_permission(current_user.id, card.project_id):
            return jsonify({'success': False, 'error': '无权查看此卡片'}), 403
        
        # 获取该卡片的所有关联关系（包括已移除的）
        relations = CardPlanRelation.query.filter_by(card_id=card_id).order_by(
            CardPlanRelation.added_at.desc()
        ).all()
        
        # 获取计划信息
        history = []
        for rel in relations:
            plan = Plan.query.get(rel.plan_id)
            if plan:
                history.append({
                    'relation_id': rel.id,
                    'plan_id': _json_snowflake_id(rel.plan_id),
                    'plan_name': plan.name,
                    'relation_type': rel.relation_type,
                    'status_in_plan': rel.status_in_plan,
                    'added_at': rel.added_at.isoformat() if rel.added_at else None,
                    'removed_at': rel.removed_at.isoformat() if rel.removed_at else None,
                    'is_current': rel.removed_at is None and rel.plan_id == card.plan_id
                })
        
        return jsonify({
            'success': True,
            'data': history
        })
    
    except Exception as e:
        print(f"❌ 获取卡片历史失败: {e}")
        return jsonify({'success': False, 'error': f'获取卡片历史失败: {str(e)}'}), 500

# CORS已在上面配置，这里不需要重复配置

