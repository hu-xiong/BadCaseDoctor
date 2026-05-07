"""删除「遗留源表」中在 Card 层没有对应关系的记录。

认定「仍有 Card 承接」的任一条件成立即保留：
- Bug：bug.card_id 指向本项目下存在的 Card；或 Card(source_type=bug, source_id=bug.id)
- BadCase：Card(source_type∈bad_case/badcase, source_id=bad_case.id)
- TestCase：Card(source_type∈test_case/testcase, source_id=test_case.id)

删除前先删 comment（badcase_id），避免外键。

用法：python tools/delete_legacy_rows_without_card.py
可选：DRY_RUN=1 python tools/delete_legacy_rows_without_card.py 只打印不删
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from sqlalchemy import and_, exists, not_, or_

from app import app, db, BadCase, Bug, Card, Comment, TestCase


def main() -> int:
    dry = os.getenv("DRY_RUN", "").strip() in ("1", "true", "yes")

    with app.app_context():
        card_bug_fk = exists().where(
            and_(
                Bug.card_id.isnot(None),
                Card.id == Bug.card_id,
                Card.project_id == Bug.project_id,
            )
        )
        card_bug_src = exists().where(
            and_(
                Card.project_id == Bug.project_id,
                Card.source_type.in_(["bug"]),
                Card.source_id == Bug.id,
            )
        )
        orphan_bugs_q = Bug.query.filter(not_(or_(card_bug_fk, card_bug_src)))

        card_bc_src = exists().where(
            and_(
                Card.project_id == BadCase.project_id,
                Card.source_type.in_(["bad_case", "badcase"]),
                Card.source_id == BadCase.id,
            )
        )
        orphan_bc_q = BadCase.query.filter(not_(card_bc_src))

        card_tc_src = exists().where(
            and_(
                Card.project_id == TestCase.project_id,
                Card.source_type.in_(["test_case", "testcase"]),
                Card.source_id == TestCase.id,
            )
        )
        orphan_tc_q = TestCase.query.filter(not_(card_tc_src))

        bug_ids = [r[0] for r in orphan_bugs_q.with_entities(Bug.id).all()]
        bc_ids = [r[0] for r in orphan_bc_q.with_entities(BadCase.id).all()]
        tc_ids = [r[0] for r in orphan_tc_q.with_entities(TestCase.id).all()]

        print(f"[INFO] DRY_RUN={dry}")
        print(f"[INFO] 待删 Bug（无 Card 承接）: {len(bug_ids)} ids={bug_ids[:40]}{'...' if len(bug_ids) > 40 else ''}")
        print(f"[INFO] 待删 BadCase（无 Card 承接）: {len(bc_ids)} ids={bc_ids[:40]}{'...' if len(bc_ids) > 40 else ''}")
        print(f"[INFO] 待删 TestCase（无 Card 承接）: {len(tc_ids)} ids={tc_ids[:40]}{'...' if len(tc_ids) > 40 else ''}")

        if dry:
            print("[OK] DRY_RUN 未写入数据库")
            return 0

        n_comm = 0
        if bc_ids:
            n_comm = Comment.query.filter(Comment.badcase_id.in_(bc_ids)).delete(synchronize_session=False)

        n_bc = orphan_bc_q.delete(synchronize_session=False) if bc_ids else 0
        n_bug = orphan_bugs_q.delete(synchronize_session=False) if bug_ids else 0
        n_tc = orphan_tc_q.delete(synchronize_session=False) if tc_ids else 0

        db.session.commit()
        print(f"[OK] comment={n_comm}, bad_case={n_bc}, bug={n_bug}, test_case={n_tc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
