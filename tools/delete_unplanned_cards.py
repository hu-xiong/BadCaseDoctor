"""删除「未计划」工作项：仅 Bug / BadCase / 测试用例 三类 Card，并清理遗留源表行。

条件：Card.plan_id 为 NULL 或 0，且 type 为 bug / badcase / testcase。
另删除 bug / bad_case / test_case 表中 plan_id 为空或 0 的记录（与主界面未计划一致）。

顺序：card_plan_relation → 解除 bug.card_id → 删 Card → 删遗留 Bug/BadCase/TestCase。

用法（项目根目录）：python tools/delete_unplanned_cards.py
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app import app, db, BadCase, Bug, Card, CardPlanRelation, CardType, TestCase


def _unplanned_plan_filter(model):
    return db.or_(model.plan_id.is_(None), model.plan_id == 0)


def main() -> int:
    with app.app_context():
        unplanned = Card.query.filter(
            _unplanned_plan_filter(Card),
            Card.type.in_([CardType.BUG, CardType.BADCASE, CardType.TESTCASE]),
        )
        n = unplanned.count()
        ids = [row[0] for row in unplanned.with_entities(Card.id).all()]
        print(
            f"[INFO] 未计划卡片（bug/badcase/testcase）数量: {n}, ids 示例: {ids[:20]}{'...' if len(ids) > 20 else ''}"
        )

        rel_deleted = 0
        bug_cleared = 0
        card_deleted = 0
        if ids:
            rel_deleted = CardPlanRelation.query.filter(CardPlanRelation.card_id.in_(ids)).delete(
                synchronize_session=False
            )
            bug_cleared = Bug.query.filter(Bug.card_id.in_(ids)).update(
                {Bug.card_id: None}, synchronize_session=False
            )
            card_deleted = Card.query.filter(Card.id.in_(ids)).delete(synchronize_session=False)

        bug_legacy = Bug.query.filter(_unplanned_plan_filter(Bug)).delete(synchronize_session=False)
        bc_legacy = BadCase.query.filter(_unplanned_plan_filter(BadCase)).delete(synchronize_session=False)
        tc_legacy = TestCase.query.filter(_unplanned_plan_filter(TestCase)).delete(synchronize_session=False)

        db.session.commit()
        print(
            f"[OK] card_plan_relation={rel_deleted}, bug.card_id 清空={bug_cleared}, card 删除={card_deleted}"
        )
        print(
            f"[OK] 遗留表删除: bug={bug_legacy}, bad_case={bc_legacy}, test_case={tc_legacy}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
