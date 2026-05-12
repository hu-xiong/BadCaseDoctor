# -*- coding: utf-8 -*-
"""一次性清理：复制「登录bug1」产生的重复/脏 Bug（按精确标题匹配）。

用法：
  python scripts/cleanup_copy_bug1_junk.py [project_id]

默认 project_id=1。删除前打印命中行，确认后提交。
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from sqlalchemy import or_

from app import app, db  # noqa: E402
from app import Bug, BugComment, Card, CardPlanRelation  # noqa: E402

# 红框内待删标题（精确匹配）；保留「登录bug1」「一个测试的bug」等
TITLES = (
    "登录bug6",
    "登录bug5",
    "登录bug4",
    "登录bug3",
    "登录忘记密码有问题",
)


def _delete_cards_for_bug(bug: Bug) -> list[int]:
    """删除与本 Bug 绑定的 Card（含 card_plan_relation）；若另有 Bug 仍引用该 Card 则跳过删卡。"""
    deleted_card_ids: list[int] = []
    cid = getattr(bug, "card_id", None)
    candidates: set[int] = set()
    if cid:
        try:
            candidates.add(int(cid))
        except (TypeError, ValueError):
            pass
    for row in (
        Card.query.filter(Card.source_id == bug.id)
        .filter(or_(Card.source_type == "bug", Card.source_type == "BUG"))
        .all()
    ):
        candidates.add(int(row.id))

    bid = int(bug.id)
    for card_id in sorted(candidates):
        other = Bug.query.filter(Bug.card_id == card_id, Bug.id != bid).first()
        if other:
            print(f"  跳过删 Card id={card_id}（仍被 Bug id={other.id} 引用）")
            continue
        CardPlanRelation.query.filter(CardPlanRelation.card_id == card_id).delete(
            synchronize_session=False
        )
        c = db.session.get(Card, card_id)
        if c:
            db.session.delete(c)
            deleted_card_ids.append(card_id)
            print(f"  已删 Card id={card_id}")
    return deleted_card_ids


def main() -> None:
    project_id = int(sys.argv[1]) if len(sys.argv) > 1 else 1

    with app.app_context():
        q = Bug.query.filter(Bug.project_id == project_id, Bug.title.in_(TITLES))
        bugs = q.order_by(Bug.id.asc()).all()
        if not bugs:
            print(f"未找到 project_id={project_id} 且标题在 {TITLES!r} 中的 Bug")
            return

        print(f"即将删除 {len(bugs)} 条 Bug（project_id={project_id}）：")
        for b in bugs:
            print(f"  Bug id={b.id} title={b.title!r} plan_id={b.plan_id} card_id={getattr(b, 'card_id', None)}")

        for b in bugs:
            n = BugComment.query.filter(BugComment.bug_id == b.id).delete(synchronize_session=False)
            if n:
                print(f"Bug id={b.id}: 删除评论 {n} 条")
            _delete_cards_for_bug(b)
            db.session.delete(b)
            print(f"已标记删除 Bug id={b.id}")

        db.session.commit()
        print("完成，已提交。")


if __name__ == "__main__":
    main()
