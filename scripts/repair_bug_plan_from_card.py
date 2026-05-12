"""
将 bug.plan_id 与已关联 Card 的 plan_id 对齐，修复「列表在子迭代、Bug 行上 plan 仍是根/空」等脏数据。
默认 dry-run，仅打印；加 --apply 才写库。

  python scripts/repair_bug_plan_from_card.py
  python scripts/repair_bug_plan_from_card.py --apply
"""
import os
import sys

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)

from app import app, db, Bug, Card  # noqa: E402


def run(dry_run: bool = True) -> int:
    n = 0
    with app.app_context():
        rows = Bug.query.filter(Bug.card_id.isnot(None)).all()
        for bug in rows:
            c = db.session.get(Card, int(bug.card_id))
            if c is None:
                continue
            cp = getattr(c, "plan_id", None)
            if cp is None or int(cp or 0) <= 0:
                continue
            cp = int(cp)
            bp = bug.plan_id
            if bp == cp:
                continue
            print(f"bug id={bug.id} plan_id {bp!r} -> {cp} (card_id={c.id})")
            if not dry_run:
                bug.plan_id = cp
            n += 1
        if not dry_run and n:
            db.session.commit()
    print(f"{'[dry-run] 将' if dry_run else '已'}更新 {n} 条 Bug.plan_id")
    return n


if __name__ == "__main__":
    apply_write = "--apply" in sys.argv
    run(dry_run=not apply_write)
