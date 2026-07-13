"""
app_services/plan_helpers.py
"""
from __future__ import annotations

    """
    返回某项目下，以 root_plan_id 为根的迭代子树中全部计划 id（含根自身）。
    列表页选中顶层「迭代」时，前端传的是根计划 id；卡片 plan_id 往往在子计划下，
    仅用 Card.plan_id == 根 id 会漏数据。
    """
    rows = db.session.query(Plan.id, Plan.parent_id).filter(Plan.project_id == project_id).all()
    children_map = {}
    for pid, parent_id in rows:
        if parent_id is not None:
            children_map.setdefault(parent_id, []).append(pid)
    out = []
    stack = [root_plan_id]
    seen = set()
    while stack:
        pid = stack.pop()
        if pid in seen:
            continue
        seen.add(pid)
        out.append(pid)
        for cid in children_map.get(pid, ()):
            stack.append(cid)
    return out


def _detach_plan_work_items(plan_id: int) -> dict:
    """
    删除迭代前解绑仍挂在该 plan_id 上的工作项与卡片。
    看板按 Card.plan_id 展示；源表 Bug/BadCase/TestCase 可能仍带 plan_id（卡片已删等），
    不解绑会导致「列表为空却无法删计划」。
    """
    pid = int(plan_id)
    n_bc = (
        BadCase.query.filter_by(plan_id=pid)
        .update({BadCase.plan_id: None}, synchronize_session=False)
    )
    n_bug = Bug.query.filter_by(plan_id=pid).update({Bug.plan_id: None}, synchronize_session=False)
    n_tc = (
        TestCase.query.filter_by(plan_id=pid)
        .update({TestCase.plan_id: None}, synchronize_session=False)
    )
    n_card = Card.query.filter_by(plan_id=pid).update({Card.plan_id: None}, synchronize_session=False)
    n_rel = CardPlanRelation.query.filter_by(plan_id=pid).delete(synchronize_session=False)
    return {
        'detached_badcases': int(n_bc or 0),
        'detached_bugs': int(n_bug or 0),
        'detached_testcases': int(n_tc or 0),
        'detached_cards': int(n_card or 0),
        'removed_card_plan_relations': int(n_rel or 0),
    }


